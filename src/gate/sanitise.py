"""Sanitiser for every published file. See docs/ARCHITECTURE.md section 7.3.

Absolute paths, the build host name and email addresses are replaced with
placeholders, and the environment keys of an Inspect log are dropped. It runs
over `runs/`, `site/inspect/`, `data.json` and `data_b.json` before publish.
"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any

PATH_RE = re.compile(r"/(?:Users|home|tmp|private)/[^\s\"']+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

PATH_PLACEHOLDER = "<path>"
HOST_PLACEHOLDER = "<host>"
EMAIL_PLACEHOLDER = "<email>"

#: JSON keys removed anywhere inside an Inspect log or a metadata block.
DROPPED_KEYS = frozenset({"env", "environment", "hostname", "user", "cwd", "argv"})


def hostnames() -> list[str]:
    """Return the host name tokens to replace, longest first.

    The short name is included so that `mac.local` and `mac` are both cleaned.
    """
    name = socket.gethostname()
    parts = {name, name.split(".")[0]}
    return sorted((p for p in parts if len(p) > 2), key=len, reverse=True)


def sanitise_text(text: str, *, hosts: list[str] | None = None) -> str:
    """Clean one string: absolute paths, host names and email addresses."""
    hosts = hostnames() if hosts is None else hosts
    text = EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    text = PATH_RE.sub(PATH_PLACEHOLDER, text)
    for host in hosts:
        text = re.sub(re.escape(host), HOST_PLACEHOLDER, text, flags=re.IGNORECASE)
    return text


def sanitise_obj(obj: Any, *, hosts: list[str] | None = None) -> Any:
    """Clean a JSON compatible structure, dropping the environment keys."""
    hosts = hostnames() if hosts is None else hosts
    if isinstance(obj, str):
        return sanitise_text(obj, hosts=hosts)
    if isinstance(obj, dict):
        return {
            k: sanitise_obj(v, hosts=hosts)
            for k, v in obj.items()
            if k not in DROPPED_KEYS
        }
    if isinstance(obj, list):
        return [sanitise_obj(v, hosts=hosts) for v in obj]
    return obj


def sanitise_json_file(path: Path | str) -> bool:
    """Clean a JSON file in place. Returns True when the file changed."""
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(original)
    except json.JSONDecodeError:
        cleaned = sanitise_text(original)
        if cleaned != original:
            path.write_text(cleaned, encoding="utf-8")
            return True
        return False
    cleaned_payload = sanitise_obj(payload)
    cleaned = json.dumps(cleaned_payload, sort_keys=True, indent=2) + "\n"
    if cleaned != original:
        path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def sanitise_tree(root: Path | str, *, suffixes: tuple[str, ...] = (".json",)) -> list[Path]:
    """Clean every matching file under `root`. Returns the changed paths, sorted."""
    root = Path(root)
    changed: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in suffixes and sanitise_json_file(path):
            changed.append(path)
    return changed
