"""Sentry webhook → Lockstep remediation pipeline.

When Sentry creates a new issue, this server receives the payload, builds
a prompt from the error context, and runs plan_task() to surface the
libraries and docs needed to fix the error.

Quick start:
  1. python3 webhook.py          (starts on port 8001)
  2. ngrok http 8001             (exposes a public URL)
  3. Sentry → Settings → Integrations → Webhooks → add <ngrok-url>/sentry/webhook
  4. Optionally add SENTRY_WEBHOOK_SECRET to .env for request signing

Output: remediation_log.jsonl in the project root + stdout
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sentry_sdk
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Response

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lockstep.webhook")

LOG_FILE = Path(__file__).parent / "remediation_log.jsonl"

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.SENTRY_ENVIRONMENT,
        traces_sample_rate=1.0,
        release="lockstep@0.1.0",
    )

app = FastAPI(title="Lockstep Sentry Webhook", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Signature verification (HMAC-SHA256)
# ---------------------------------------------------------------------------

def _verify(body: bytes, signature: str | None) -> bool:
    secret = config.SENTRY_WEBHOOK_SECRET
    if not secret:
        return True  # dev mode: no secret configured → accept all
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_PLATFORM_TO_ECOSYSTEM = {
    "python": "pypi",
    "javascript": "npm",
    "node": "npm",
    "node-express": "npm",
    "rust": "cargo",
    "go": "go",
}


def _build_prompt(issue: dict) -> tuple[str, str | None]:
    """Return (prompt, ecosystem) derived from a Sentry issue dict."""
    title = issue.get("title", "Unknown error")
    meta = issue.get("metadata", {})
    error_type = meta.get("type", "")
    error_value = meta.get("value", "")
    culprit = issue.get("culprit", "")
    platform = issue.get("platform", "")
    ecosystem = _PLATFORM_TO_ECOSYSTEM.get(platform)

    parts = [f"Fix this error: {title}"]
    if error_type and error_value:
        parts.append(f"Exception — {error_type}: {error_value}")
    elif error_value:
        parts.append(f"Details: {error_value}")
    if culprit:
        parts.append(f"Location: {culprit}")
    parts.append("Which libraries or patterns should I use to handle or resolve this?")

    return ". ".join(parts), ecosystem


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@app.post("/sentry/webhook")
async def sentry_webhook(
    request: Request,
    sentry_hook_signature: str | None = Header(None, alias="sentry-hook-signature"),
):
    body = await request.body()

    if not _verify(body, sentry_hook_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = payload.get("action")
    if action != "created":
        return Response(status_code=204)  # silently ignore non-create events

    issue = payload.get("data", {}).get("issue", {})
    issue_id = issue.get("id", "unknown")
    title = issue.get("title", "Unknown error")
    issue_url = issue.get("permalink") or ""
    level = issue.get("level", "error")

    log.info("=" * 60)
    log.info(f"Sentry [{level.upper()}] #{issue_id}: {title}")
    if issue_url:
        log.info(f"URL: {issue_url}")

    prompt, ecosystem = _build_prompt(issue)
    log.info(f"Prompt: {prompt[:120]}...")

    with sentry_sdk.start_transaction(
        op="webhook.remediation", name="sentry_issue_remediation"
    ) as txn:
        txn.set_tag("sentry.issue_id", issue_id)
        txn.set_tag("sentry.level", level)
        txn.set_tag("ecosystem", ecosystem or "any")

        try:
            from tools.plan import plan_task

            with sentry_sdk.start_span(
                op="mcp.tool", description="plan_task for error remediation"
            ):
                plan = plan_task(
                    prompt=prompt,
                    ecosystem=ecosystem,
                    session_id=f"sentry:{issue_id}",
                )
            entry_count = len(plan.get("plan", []))
            txn.set_data("plan_entry_count", entry_count)
            txn.set_tag("remediation.status", "success")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            log.error(f"plan_task failed: {e}")
            plan = {"error": str(e), "plan": []}
            entry_count = 0
            txn.set_tag("remediation.status", "failed")

    # Persist to JSONL
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sentry_issue_id": issue_id,
        "sentry_level": level,
        "sentry_url": issue_url,
        "title": title,
        "prompt": prompt,
        "plan": plan,
    }
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")

    # Human-readable summary
    log.info(f"Remediation plan ({entry_count} steps):")
    for i, entry in enumerate(plan.get("plan", []), 1):
        lib = entry.get("library_id") or "none"
        source = entry.get("source", "?")
        task_text = (entry.get("task") or "")[:80]
        log.info(f"  [{i}] {lib}  ({source})  — {task_text}")
    log.info(f"Full plan → {LOG_FILE}")
    log.info("=" * 60)

    return {"status": "ok", "issue_id": issue_id, "plan_entries": entry_count}


@app.get("/health")
def health():
    return {"status": "ok", "service": "lockstep-webhook"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", "8001"))
    log.info(f"Lockstep webhook server starting on port {port}")
    log.info("Expose publicly:  ngrok http %d", port)
    log.info("Sentry endpoint:  POST /sentry/webhook")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
