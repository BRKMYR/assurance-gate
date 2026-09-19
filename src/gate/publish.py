"""`gate publish`. See docs/ARCHITECTURE.md section 8.

Three destinations, one command:

1. the static Space `N20X/assurance-gate` gets the contents of `site/`,
2. the dataset `N20X/assurance-gate-runs` gets the public run records,
3. a checkout of the website repository gets a mirror of `site/` under
   `gate/live/`, and only when `MIRROR_TOKEN` is set.

`--dry-run` prints every operation and touches nothing. Without `HF_TOKEN` a
real run refuses with exit code 2 instead of half publishing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from huggingface_hub import HfApi


def _resolve_token() -> str | None:
    """HF_TOKEN from the environment, else the token stored by `hf auth login`."""
    import os
    from huggingface_hub import get_token

    return os.environ.get("HF_TOKEN") or get_token()


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SPACE_REPO_ID = "N20X/assurance-gate"
DATASET_REPO_ID = "N20X/assurance-gate-runs"

SITE_DIR = "site"
SPACE_CARD = "space/README.md"
DATASET_CARD = "dataset/README.md"
DATASET_ALLOW_PATTERNS: tuple[str, ...] = (
    "runs/**/results.json",
    "runs/**/manifest.json",
    "preregistration/*.json",
)

MIRROR_SUBDIR = "gate/live"
MIRROR_REMOTE = "github.com/BRKMYR/brkmyr.com"
DEFAULT_MIRROR_CHECKOUT = "~/src/github.com/BRKMYR/brkmyr.com"
GIT_IDENTITY = ("NKLS BRKMYR", "BRKMYR@users.noreply.github.com")

EXIT_OK = 0
EXIT_NO_TOKEN = 2


def utc_now() -> str:
    """Publish timestamp, ISO 8601 UTC with a Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit_message(tag: str, when: str) -> str:
    """Commit message format of section 8."""
    return f"gate publish {tag} {when}"


def dataset_files(root: Path) -> list[Path]:
    """Every public run record that goes to the dataset, sorted."""
    found: list[Path] = []
    for pattern in DATASET_ALLOW_PATTERNS:
        found.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(found))


def mirror_checkout(root: Path) -> Path:
    override = os.environ.get("MIRROR_CHECKOUT")
    if override:
        return Path(override).expanduser()
    return Path(DEFAULT_MIRROR_CHECKOUT).expanduser()


def build_plan(root: Path, tag: str, when: str) -> list[str]:
    """Human readable operation list. The dry run prints exactly this."""
    message = commit_message(tag, when)
    site = root / SITE_DIR
    records = dataset_files(root)
    plan = [
        f"space upload_folder {site} -> {SPACE_REPO_ID} (delete_patterns=['*'])",
        f"space upload_file {SPACE_CARD} -> {SPACE_REPO_ID}:README.md",
        f"dataset upload_folder {root} -> {DATASET_REPO_ID} "
        f"(allow_patterns={list(DATASET_ALLOW_PATTERNS)}, {len(records)} files matched)",
        f"dataset upload_file {DATASET_CARD} -> {DATASET_REPO_ID}:README.md",
    ]
    for record in records:
        plan.append(f"dataset file {record.relative_to(root)}")
    if os.environ.get("MIRROR_TOKEN"):
        checkout = mirror_checkout(root)
        plan.append(f"mirror copy {site} -> {checkout / MIRROR_SUBDIR}")
        plan.append(f"mirror commit in {checkout}: {message}")
        plan.append(f"mirror push {MIRROR_REMOTE}")
    else:
        plan.append("mirror skipped: MIRROR_TOKEN is not set")
    plan.append(f"commit message: {message}")
    return plan


def publish_space(api: HfApi, root: Path, message: str) -> None:
    api.upload_folder(
        folder_path=str(root / SITE_DIR),
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        commit_message=message,
        delete_patterns=["*"],
    )
    # The folder upload cleared the repository, so the card goes back last.
    api.upload_file(
        path_or_fileobj=str(root / SPACE_CARD),
        path_in_repo="README.md",
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        commit_message=message,
    )


def publish_dataset(api: HfApi, root: Path, message: str) -> None:
    api.upload_folder(
        folder_path=str(root),
        repo_id=DATASET_REPO_ID,
        repo_type="dataset",
        commit_message=message,
        allow_patterns=list(DATASET_ALLOW_PATTERNS),
    )
    api.upload_file(
        path_or_fileobj=str(root / DATASET_CARD),
        path_in_repo="README.md",
        repo_id=DATASET_REPO_ID,
        repo_type="dataset",
        commit_message=message,
    )


def _git(checkout: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def mirror_site(root: Path, message: str, token: str) -> None:
    checkout = mirror_checkout(root)
    if not (checkout / ".git").is_dir():
        print(f"gate publish: mirror checkout missing at {checkout}, skipped")
        return
    target = checkout / MIRROR_SUBDIR
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(root / SITE_DIR, target)
    name, email = GIT_IDENTITY
    _git(checkout, "add", MIRROR_SUBDIR)
    status = _git(checkout, "status", "--porcelain", MIRROR_SUBDIR)
    if not status.stdout.strip():
        print("gate publish: mirror unchanged, nothing to commit")
        return
    _git(checkout, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-m", message)
    _git(checkout, "push", f"https://x-access-token:{token}@{MIRROR_REMOTE}", "HEAD")


def run(args: argparse.Namespace) -> int:
    root = Path(getattr(args, "root", None) or REPO_ROOT)
    when = utc_now()
    message = commit_message(args.tag, when)
    plan = build_plan(root, args.tag, when)

    if args.dry_run:
        print(f"gate publish --tag {args.tag} --dry-run. Nothing is uploaded.")
        for step in plan:
            print(f"  {step}")
        return EXIT_OK

    token = _resolve_token()
    if not token:
        print(
            "gate publish: no Hugging Face token found (HF_TOKEN or `hf auth login`). Set a token with write scope on "
            f"{SPACE_REPO_ID} and {DATASET_REPO_ID}, or run with --dry-run.",
        )
        return EXIT_NO_TOKEN

    api = HfApi(token=token)
    publish_space(api, root, message)
    publish_dataset(api, root, message)

    mirror_token = os.environ.get("MIRROR_TOKEN")
    if mirror_token:
        mirror_site(root, message, mirror_token)
    else:
        print("gate publish: MIRROR_TOKEN is not set, mirror skipped")

    for step in plan:
        print(f"  {step}")
    print(f"gate publish: done, {message}")
    return EXIT_OK


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "publish",
        help="Upload the built site to the Space, the runs to the dataset, and mirror the site.",
    )
    parser.add_argument("--tag", required=True, help="release tag, for example v1.0")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print every operation and touch nothing",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.set_defaults(func=run)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gate publish")
    subparsers = parser.add_subparsers()
    register(subparsers)
    args = parser.parse_args(["publish", *(argv or [])])
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
