#!/usr/bin/env python3
"""
plan_monitor.py — Live view of every plan_task decision made by the MCP server.

Tails .lockstep_activity.jsonl and prints each library selection in real time,
showing the same TASK / WHY / USES / CACHE output as the test harness but live
while Claude Code is running.

Run in a separate terminal while Claude Code is active:
    python scripts/plan_monitor.py

Three-terminal demo setup:
    Terminal 1:  python scripts/cache_inspector.py --watch 3
    Terminal 2:  cd ~/stock-predictor-demo && ~/.local/bin/claude
    Terminal 3:  python scripts/plan_monitor.py          ← this script
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".lockstep_activity.jsonl")

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
CYAN    = "\033[36m"
YELLOW  = "\033[33m"
MAGENTA = "\033[35m"
RED     = "\033[31m"
BLUE    = "\033[34m"
WHITE   = "\033[97m"


def _bar(prob: float, width: int = 12) -> str:
    filled = round(prob * width)
    return "█" * filled + "░" * (width - filled)


def _src_icon(src: str) -> str:
    if src == "cache":
        return f"{GREEN}💾 CACHE   {RESET}"
    if src == "supabase":
        return f"{BLUE}🌐 SUPABASE{RESET}"
    return f"{RED}✗ NONE    {RESET}"


def render_decompose(entry: dict) -> None:
    print(f"\n{BOLD}{'═' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  NEW PROMPT  {entry['ts']}{RESET}")
    print(f"{BOLD}{'═' * 72}{RESET}")
    print(f"  {DIM}{entry.get('prompt', '')[:100]}...{RESET}")
    subtasks = entry.get("subtasks", [])
    print(f"\n  Claude decomposed into {len(subtasks)} subtask(s):")
    for i, s in enumerate(subtasks, 1):
        print(f"    {DIM}{i}.{RESET} {s[:90]}")
    print()


def render_resolve(entry: dict) -> None:
    src = entry.get("source", "?")
    lib = entry.get("library_id") or "none"
    ver = entry.get("version") or "?"
    prob = entry.get("probability") or 0.0
    task = entry.get("subtask", "")
    why = entry.get("why", "")
    key_fn = entry.get("key_function", "")
    candidates = entry.get("cache_candidates", [])
    ts = entry.get("ts", "")

    src_icon = _src_icon(src)
    prob_str = f"p={prob:.3f}" if prob else "      "
    bar = _bar(prob)

    print(f"  {ts}  {src_icon}  {BOLD}{lib:<32}{RESET} v{ver}")
    print(f"           {YELLOW}prob:{RESET} {prob_str}  {bar}")
    print(f"           {YELLOW}TASK:{RESET} {task[:95]}")

    if src == "cache":
        print(f"           {GREEN}WHY: {RESET} Served from Redis cache — no Supabase call")
    else:
        print(f"           {YELLOW}WHY: {RESET} {why[:90]}")

    if key_fn:
        print(f"           {YELLOW}USES:{RESET} {key_fn[:95]}")

    if candidates and src != "cache":
        top = [c for c in candidates if c.get("probability", 0) >= 0.20][:4]
        if top:
            parts = []
            for c in top:
                kw = f"{MAGENTA}+kw{RESET}" if c.get("keyword_boost", 0) > 0 else ""
                parts.append(f"{c['library_id']}(p={c['probability']:.3f}{kw})")
            print(f"           {DIM}cache scanned: {', '.join(parts)}{RESET}")

    print()


def tail_log(path: str) -> None:
    print(f"\n{BOLD}  Lockstep Plan Monitor{RESET}")
    print(f"  Watching: {path}")
    print(f"  Scan threshold: {config.CACHE_SCAN_THETA}  |  TTL: {config.RECO_TTL_SECONDS}s")
    print(f"\n{DIM}  Waiting for Claude Code to call lockstep:plan_task ...{RESET}\n")

    # Seek to end of existing file so we only show new activity
    pos = 0
    if os.path.exists(path):
        with open(path) as f:
            f.seek(0, 2)
            pos = f.tell()

    while True:
        try:
            if not os.path.exists(path):
                time.sleep(0.5)
                continue

            with open(path) as f:
                f.seek(pos)
                new_data = f.read()
                pos = f.tell()

            for line in new_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    event = entry.get("event")
                    if event == "decompose":
                        render_decompose(entry)
                    elif event == "resolve":
                        render_resolve(entry)
                except json.JSONDecodeError:
                    pass

            time.sleep(0.3)

        except KeyboardInterrupt:
            print(f"\n{DIM}  Stopped.{RESET}\n")
            sys.exit(0)


if __name__ == "__main__":
    tail_log(LOG_PATH)
