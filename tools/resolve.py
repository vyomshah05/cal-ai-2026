"""resolve_version — lockfile parsers.

Pure parsing — no network, no DB. Supports:
  package-lock.json   (npm)
  yarn.lock           (npm)
  requirements.txt    (pypi)
  poetry.lock         (pypi)
  Cargo.lock          (cargo)
  go.mod              (go)

Input: either manifest_files=[{filename, content}] (for HTTP transport) OR
project_root (local path, for stdio). If both are given, manifest_files takes
precedence.

Output: {
    resolved: [{library_id, requested_range, locked_version, source_file}],
    unresolved: [{name, reason, source_file}]
}
library_id is "{ecosystem}:{name}" lowercased — valid input to get_versioned_docs.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import sentry_sdk

# ---------------------------------------------------------------------------
# npm: package-lock.json v2/v3
# ---------------------------------------------------------------------------

def _parse_package_lock(content: str, source_file: str) -> tuple[list, list]:
    resolved, unresolved = [], []
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        return [], [{"name": "package-lock.json", "reason": f"parse error: {e}", "source_file": source_file}]

    # v2/v3 uses "packages" key; v1 uses "dependencies"
    packages = data.get("packages", {})
    if packages:
        for pkg_path, info in packages.items():
            if not pkg_path or pkg_path == "":
                continue
            # pkg_path like "node_modules/react" or "node_modules/@scope/pkg"
            name = re.sub(r"^node_modules/", "", pkg_path)
            version = info.get("version", "")
            if not version:
                unresolved.append({"name": name, "reason": "no version in packages entry", "source_file": source_file})
                continue
            resolved.append({
                "library_id": f"npm:{name.lower()}",
                "requested_range": info.get("resolved", ""),
                "locked_version": version,
                "source_file": source_file,
            })
    else:
        deps = data.get("dependencies", {})
        for name, info in deps.items():
            version = info.get("version", "")
            if not version:
                unresolved.append({"name": name, "reason": "no version in dependencies entry", "source_file": source_file})
                continue
            resolved.append({
                "library_id": f"npm:{name.lower()}",
                "requested_range": info.get("requires", {}).get(name, ""),
                "locked_version": version,
                "source_file": source_file,
            })
    return resolved, unresolved


# ---------------------------------------------------------------------------
# npm: yarn.lock
# ---------------------------------------------------------------------------

def _parse_yarn_lock(content: str, source_file: str) -> tuple[list, list]:
    resolved, unresolved = [], []
    current_names: list[str] = []
    version = None

    for line in content.splitlines():
        # Block header: `"pkg@^1.0.0", "pkg@~1.0.0":` or `pkg@^1.0.0:`
        if line and not line.startswith(" ") and not line.startswith("#"):
            if current_names and version:
                for name in current_names:
                    resolved.append({
                        "library_id": f"npm:{name.lower()}",
                        "requested_range": "",
                        "locked_version": version,
                        "source_file": source_file,
                    })
            current_names = []
            version = None
            # Extract package names from header
            header = line.rstrip(":")
            for entry in re.split(r",\s*", header):
                entry = entry.strip().strip('"')
                m = re.match(r"^(@?[^@]+)@", entry)
                if m:
                    current_names.append(m.group(1))
        elif line.strip().startswith("version "):
            m = re.match(r'\s+version\s+"?([^"\s]+)"?', line)
            if m:
                version = m.group(1)

    if current_names and version:
        for name in current_names:
            resolved.append({
                "library_id": f"npm:{name.lower()}",
                "requested_range": "",
                "locked_version": version,
                "source_file": source_file,
            })

    # Deduplicate by library_id (same package, multiple ranges → same locked ver)
    seen: dict[str, dict] = {}
    for r in resolved:
        seen[r["library_id"]] = r
    return list(seen.values()), unresolved


# ---------------------------------------------------------------------------
# pypi: requirements.txt
# ---------------------------------------------------------------------------

_REQ_COMMENT = re.compile(r"\s*#.*$")
_REQ_LINE = re.compile(
    r"^([A-Za-z0-9_.\-\[\]]+?)"          # package name (with optional extras)
    r"\s*(?:==|===)\s*"                    # pinned operator
    r"([A-Za-z0-9_.+\-]+)"               # version
)
_REQ_RANGE = re.compile(r"^([A-Za-z0-9_.\-\[\]]+?)\s*([><=!~^].+)$")


def _normalize_pypi_name(name: str) -> str:
    # strip extras like [security]
    return re.sub(r"\[.*?\]", "", name).lower().replace("-", "_")


def _parse_requirements_txt(content: str, source_file: str) -> tuple[list, list]:
    resolved, unresolved = [], []
    for raw in content.splitlines():
        line = _REQ_COMMENT.sub("", raw).strip()
        if not line or line.startswith("-r") or line.startswith("--") or line.startswith("git+"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            resolved.append({
                "library_id": f"pypi:{_normalize_pypi_name(m.group(1))}",
                "requested_range": f"=={m.group(2)}",
                "locked_version": m.group(2),
                "source_file": source_file,
            })
        else:
            m2 = _REQ_RANGE.match(line)
            if m2:
                unresolved.append({
                    "name": _normalize_pypi_name(m2.group(1)),
                    "reason": f"not pinned: {m2.group(2)}",
                    "source_file": source_file,
                })
    return resolved, unresolved


# ---------------------------------------------------------------------------
# pypi: poetry.lock
# ---------------------------------------------------------------------------

def _parse_poetry_lock(content: str, source_file: str) -> tuple[list, list]:
    resolved, unresolved = [], []
    current: dict[str, str] = {}

    for line in content.splitlines():
        if line.strip() == "[[package]]":
            if current.get("name") and current.get("version"):
                resolved.append({
                    "library_id": f"pypi:{current['name'].lower().replace('-','_')}",
                    "requested_range": "",
                    "locked_version": current["version"],
                    "source_file": source_file,
                })
            current = {}
        else:
            m = re.match(r'^(\w+)\s*=\s*"([^"]+)"', line)
            if m:
                current[m.group(1)] = m.group(2)

    if current.get("name") and current.get("version"):
        resolved.append({
            "library_id": f"pypi:{current['name'].lower().replace('-','_')}",
            "requested_range": "",
            "locked_version": current["version"],
            "source_file": source_file,
        })
    return resolved, unresolved


# ---------------------------------------------------------------------------
# cargo: Cargo.lock
# ---------------------------------------------------------------------------

def _parse_cargo_lock(content: str, source_file: str) -> tuple[list, list]:
    resolved = []
    current: dict[str, str] = {}

    for line in content.splitlines():
        if line.strip() == "[[package]]":
            if current.get("name") and current.get("version"):
                resolved.append({
                    "library_id": f"cargo:{current['name'].lower()}",
                    "requested_range": "",
                    "locked_version": current["version"],
                    "source_file": source_file,
                })
            current = {}
        else:
            m = re.match(r'^(\w+)\s*=\s*"([^"]+)"', line)
            if m:
                current[m.group(1)] = m.group(2)

    if current.get("name") and current.get("version"):
        resolved.append({
            "library_id": f"cargo:{current['name'].lower()}",
            "requested_range": "",
            "locked_version": current["version"],
            "source_file": source_file,
        })
    return resolved, []


# ---------------------------------------------------------------------------
# go: go.mod
# ---------------------------------------------------------------------------

_GO_REQUIRE = re.compile(r"^\s+([^\s]+)\s+v([^\s/]+)")


def _parse_go_mod(content: str, source_file: str) -> tuple[list, list]:
    resolved, unresolved = [], []
    in_require = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require and stripped == ")":
            in_require = False
            continue
        if in_require or stripped.startswith("require "):
            target = stripped[len("require "):] if stripped.startswith("require ") else stripped
            m = _GO_REQUIRE.match(f" {target}")
            if m:
                name = m.group(1).lower()
                ver = m.group(2)
                resolved.append({
                    "library_id": f"go:{name}",
                    "requested_range": f"v{ver}",
                    "locked_version": ver,
                    "source_file": source_file,
                })
    return resolved, unresolved


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PARSERS: dict[str, Any] = {
    "package-lock.json": _parse_package_lock,
    "yarn.lock": _parse_yarn_lock,
    "requirements.txt": _parse_requirements_txt,
    "poetry.lock": _parse_poetry_lock,
    "cargo.lock": _parse_cargo_lock,
    "go.mod": _parse_go_mod,
}


def _dispatch(filename: str, content: str) -> tuple[list, list]:
    key = Path(filename).name.lower()
    parser = _PARSERS.get(key)
    if parser is None:
        return [], [{"name": filename, "reason": "unsupported manifest type", "source_file": filename}]
    return parser(content, filename)


def resolve_version(
    manifest_files: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """Parse lockfiles and return pinned dependency versions.

    Args:
        manifest_files: list of {filename, content} dicts (used over HTTP).
        project_root: local path to search for known lockfiles (used over stdio).

    Returns:
        {resolved: [{library_id, requested_range, locked_version, source_file}],
         unresolved: [{name, reason, source_file}]}
    """
    with sentry_sdk.start_transaction(op="mcp.tool", name="resolve_version") as txn:
        txn.set_data("manifest_count", len(manifest_files) if manifest_files else 0)
        txn.set_tag("source", "manifest_files" if manifest_files else ("project_root" if project_root else "none"))

        all_resolved: list[dict] = []
        all_unresolved: list[dict] = []

        if manifest_files:
            for entry in manifest_files:
                with sentry_sdk.start_span(op="parse", description=f"parse {entry.get('filename', '?')}"):
                    r, u = _dispatch(entry.get("filename", ""), entry.get("content", ""))
                all_resolved.extend(r)
                all_unresolved.extend(u)
        elif project_root:
            root = Path(project_root)
            for name in _PARSERS:
                candidate = root / name
                # Also check Cargo.lock with capital C
                if not candidate.exists() and name == "cargo.lock":
                    candidate = root / "Cargo.lock"
                if candidate.exists():
                    try:
                        with sentry_sdk.start_span(op="parse", description=f"parse {name}"):
                            r, u = _dispatch(name, candidate.read_text(encoding="utf-8", errors="replace"))
                        all_resolved.extend(r)
                        all_unresolved.extend(u)
                    except OSError as e:
                        sentry_sdk.capture_exception(e)
                        all_unresolved.append({"name": name, "reason": str(e), "source_file": str(candidate)})
        else:
            all_unresolved.append({
                "name": "(none)",
                "reason": "provide either manifest_files or project_root",
                "source_file": "",
            })

        txn.set_data("resolved_count", len(all_resolved))
        txn.set_data("unresolved_count", len(all_unresolved))
        return {"resolved": all_resolved, "unresolved": all_unresolved}
