#!/bin/sh
# After `gate run --track b`: redacted public logs, viewer bundle, path scrub,
# build, lint, publish. Run from the repository root with the venv on PATH.
set -e
LOGS=${1:-logs/track_b}
PUBLIC=logs/track_b_public
rm -rf "$PUBLIC" site/inspect
python scripts/make_public_logs.py "$LOGS" "$PUBLIC"
inspect view bundle --log-dir "$PUBLIC" --output-dir site/inspect
# the bundle index embeds the absolute log directory
python - <<'PY'
import re, pathlib
for p in pathlib.Path("site/inspect").rglob("*"):
    if p.suffix in (".html", ".json", ".js", ".txt") and p.is_file():
        t = p.read_text(encoding="utf-8", errors="ignore")
        u = re.sub(r"/(?:Users|home|tmp|private)/[^\s\"']+", "<path>", t)
        if u != t:
            p.write_text(u, encoding="utf-8")
            print("scrubbed", p)
PY
gate build --out site/
python scripts/lint_copy.py --mode release
echo "finish_track_b: ready to publish"
