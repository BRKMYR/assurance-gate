#!/usr/bin/env python3
"""Publish the dashboard into the website repository at `<website>/gate/`.

The published page is the project itself. One HTML page, same origin, local
data, no iframe. The Hugging Face Space keeps serving `site/` unchanged, so
the only difference between the two builds is the inline `GATE_CONFIG` block
this script writes into `gate/index.html`.

Usage:

    .venv/bin/python scripts/publish_website.py [website_repo]

`website_repo` defaults to `../brkmyr.com` relative to this repository. The
script only ever writes inside `<website_repo>/gate/`. Files under `gate/`
that are not part of the published set are removed. No git command is run.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"

#: Single files copied verbatim.
FILES = (
    "app.js",
    "styles.css",
    "strings.json",
    "strings.required.txt",
    "casestudy.html",
    "data.json",
    "data_b.json",
)

#: Directories copied whole. `inspect/` and `dev/` stay out of the website.
DIRS = ("thumbs", "assets")

#: The Space keeps the evaluation bundle, so Track B refs point there.
INSPECT_BASE = "https://n20x-assurance-gate.static.hf.space/"

#: The website marks every project page this way. site/index.html carries no
#: robots rule because the Space is meant to be found.
ROBOTS_META = '<meta name="robots" content="noindex, nofollow, noarchive">\n'

CONFIG_SCRIPT = (
    "<script>\n"
    "  /* Published page configuration. Written by scripts/publish_website.py.\n"
    "     The Space build ships site/index.html without this block. */\n"
    "  window.GATE_CONFIG = {\n"
    '    inspectBase: "%s",\n'
    "    casestudy: true\n"
    "  };\n"
    "</script>\n"
) % INSPECT_BASE


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def page_html() -> str:
    """`site/index.html` with the configuration block added to the head."""
    text = (SITE / "index.html").read_text()
    if "GATE_CONFIG" in text:
        raise SystemExit("site/index.html already carries a GATE_CONFIG block")
    if "</head>" not in text:
        raise SystemExit("site/index.html has no head to write into")
    head = ROBOTS_META + CONFIG_SCRIPT
    return text.replace("</head>", head + "</head>", 1)


def wanted_paths() -> set[str]:
    """Every path the published set owns, relative to `gate/`."""
    out = {"index.html"}
    out.update(FILES)
    for name in DIRS:
        root = SITE / name
        if not root.is_dir():
            continue
        for item in root.rglob("*"):
            if item.is_file():
                out.add(str(item.relative_to(SITE)))
    return out


def copy_file(src: Path, dst: Path) -> bool:
    """Copy when the bytes differ. Returns True when the file was written."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and filecmp.cmp(src, dst, shallow=False):
        return False
    shutil.copy2(src, dst)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "website", nargs="?", default=str(REPO.parent / "brkmyr.com"),
        help="path to the website repository (default: ../brkmyr.com)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list what would be written and removed, and write nothing"
    )
    args = parser.parse_args()

    website = Path(args.website).resolve()
    if not website.is_dir():
        raise SystemExit(f"website repository not found: {website}")
    gate = website / "gate"
    # Everything below is confined to this one directory.
    if gate.exists() and not gate.is_dir():
        raise SystemExit(f"not a directory: {gate}")

    for name in FILES:
        if not (SITE / name).is_file():
            raise SystemExit(f"missing source file: site/{name}")

    wanted = wanted_paths()
    written: list[tuple[str, int]] = []
    unchanged = 0
    total = 0

    if not args.dry_run:
        gate.mkdir(parents=True, exist_ok=True)

    # The page first, so a half written directory never serves a stale page.
    html = page_html()
    target = gate / "index.html"
    total += len(html.encode())
    if args.dry_run:
        written.append(("index.html", len(html.encode())))
    else:
        old = target.read_text() if target.exists() else None
        if old != html:
            target.write_text(html)
            written.append(("index.html", len(html.encode())))
        else:
            unchanged += 1

    for rel in sorted(wanted - {"index.html"}):
        src = SITE / rel
        size = src.stat().st_size
        total += size
        if args.dry_run:
            written.append((rel, size))
            continue
        if copy_file(src, gate / rel):
            written.append((rel, size))
        else:
            unchanged += 1

    # Anything else under gate/ is no longer part of the project.
    removed: list[str] = []
    if gate.is_dir():
        for item in sorted(gate.rglob("*"), reverse=True):
            if item.is_file():
                rel = str(item.relative_to(gate))
                if rel not in wanted:
                    removed.append(rel)
                    if not args.dry_run:
                        item.unlink()
            elif item.is_dir() and not args.dry_run:
                try:
                    item.rmdir()
                except OSError:
                    pass

    label = "would write" if args.dry_run else "wrote"
    print(f"target: {gate}")
    for rel, size in written:
        print(f"  {label} {rel}  {human(size)}")
    if unchanged:
        print(f"  {unchanged} files already current")
    for rel in removed:
        print(f"  {'would remove' if args.dry_run else 'removed'} {rel}")
    print(f"{len(wanted)} files, {human(total)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
