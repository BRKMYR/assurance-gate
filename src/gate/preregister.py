"""`gate preregister`: freeze a gate file and publish its hash before any run.

See docs/ARCHITECTURE.md section 7.4. The command refuses when a run already
exists for the suite, when the gate file still holds an owner copy placeholder,
or when the file is not marked frozen. It then creates a GitHub release through
`gh` and, when `HF_TOKEN` is set, commits the same record to the dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gate.schema import SCHEMA_VERSION

OWNER_COPY_MARKER = "[[OWNER_COPY"
DATASET_REPO = "N20X/assurance-gate-runs"


class PreregisterRefused(RuntimeError):
    """Raised when a precondition of section 7.4 is not met."""


def utc_now() -> str:
    """Return the current time as ISO 8601 UTC with a `Z` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    """Return the SHA 256 of the whole gate file, bytes as written."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_preconditions(root: Path, suite: str, gate_file: Path) -> None:
    """Raise `PreregisterRefused` when the suite or the gate file is not ready.

    The three refusals of AC-14: an existing manifest under `runs/<suite>/`, an
    owner copy placeholder anywhere in the gate file, and a missing `frozen: true`.
    """
    if not gate_file.is_file():
        raise PreregisterRefused(f"gate file not found: {gate_file}")
    suite_dir = root / "runs" / suite
    existing = sorted(suite_dir.rglob("manifest.json")) if suite_dir.is_dir() else []
    if existing:
        raise PreregisterRefused(
            f"runs/{suite}/ already holds {len(existing)} manifest file(s); a suite cannot be preregistered after it ran"
        )
    text = gate_file.read_text(encoding="utf-8")
    if OWNER_COPY_MARKER in text:
        raise PreregisterRefused(f"{gate_file} still holds an owner copy placeholder")
    if not any(line.strip().replace(" ", "") == "frozen:true" for line in text.splitlines()):
        raise PreregisterRefused(f"{gate_file} is missing `frozen: true`")


def gh_release_create(tag: str, title: str, body: str) -> str:
    """Create a GitHub release with `gh` and return the timestamp of the call.

    Mocked in every test. The only network call in this module besides the
    optional dataset commit.
    """
    subprocess.run(
        ["gh", "release", "create", tag, "--title", title, "--notes", body],
        check=True,
        capture_output=True,
        text=True,
    )
    return utc_now()


def hf_dataset_commit(record: dict, track: str, suite: str) -> str | None:
    """Commit the preregistration record to the dataset when `HF_TOKEN` is set.

    Returns the commit timestamp, or None with a warning when no token exists.
    """
    token = os.environ.get("HF_TOKEN")
    if not token:
        print(
            "warning: HF_TOKEN is not set, the preregistration hash was not committed to the dataset",
            file=sys.stderr,
        )
        return None
    from huggingface_hub import CommitOperationAdd, HfApi

    payload = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    HfApi(token=token).create_commit(
        repo_id=DATASET_REPO,
        repo_type="dataset",
        operations=[
            CommitOperationAdd(
                path_in_repo=f"preregistration/{track}-{suite}.json",
                path_or_fileobj=payload,
            )
        ],
        commit_message=f"preregister {track} {suite}",
    )
    return utc_now()


def preregister(root: Path, track: str, suite: str) -> dict:
    """Run the full preregistration and return the record that was written."""
    gate_file = root / "gates" / f"track_{track}.yaml"
    check_preconditions(root, suite, gate_file)

    digest = sha256_of(gate_file)
    tag = f"gates-{track}-{suite}-{digest[:8]}"
    rel_path = gate_file.relative_to(root).as_posix()
    body = f"Gate file {rel_path}\nsha256 {digest}\nsuite {suite}\ntrack {track}\n"
    released_at = gh_release_create(tag, tag, body)

    record = {
        "schema_version": SCHEMA_VERSION,
        "track": track,
        "suite": suite,
        "gate_file": rel_path,
        "gate_file_sha256": digest,
        "tag": tag,
        "github_release": released_at,
        "hf_dataset_commit": None,
    }
    record["hf_dataset_commit"] = hf_dataset_commit(record, track, suite)

    out = root / "runs" / suite / "preregistration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"preregister: {tag} written to {out.relative_to(root).as_posix()}")
    return record


def _cmd(args: argparse.Namespace) -> int:
    try:
        preregister(Path(args.root).resolve(), args.track, args.suite)
    except PreregisterRefused as exc:
        print(f"preregister: refused, {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"preregister: gh failed, {exc.stderr or exc}", file=sys.stderr)
        return 1
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add the `preregister` subcommand to the CLI root."""
    parser = subparsers.add_parser(
        "preregister", help="Freeze a gate file and publish its hash before any run"
    )
    parser.add_argument("--track", choices=["a", "b"], default="a")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.set_defaults(func=_cmd)
