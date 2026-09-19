"""`gate ingest`: turn an AVSB run directory into a committed suite under `runs/`.

See docs/ARCHITECTURE.md section 7.5. The command refuses a run that started
before the gate hash was published, which is the only thing that makes the word
"pre registered" mean anything. Suite `demo` is the documented exception: it is
ingested with `preregistered: false` and the dashboard says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from gate import __version__
from gate.adapters import avsb

DEMO_SUITE = "demo"


class IngestRefused(RuntimeError):
    """Raised when a run cannot be ingested under the rules of section 7.5."""


def parse_utc(stamp: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp with a `Z` suffix."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def check_preregistration(root: Path, suite: str, generated_at: str) -> dict | None:
    """Refuse a manifest older than the published gate hash.

    Returns the preregistration record when one exists. Suite `demo` skips the
    check because the gates were written after those runs.
    """
    record_path = root / "runs" / suite / "preregistration.json"
    if not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if suite == DEMO_SUITE:
        return record
    released = record.get("github_release")
    if released and parse_utc(generated_at) < parse_utc(released):
        raise IngestRefused(
            f"run generated at {generated_at} precedes the published gate hash at {released}"
        )
    return record


def ingest(
    root: Path,
    *,
    track: str,
    suite: str,
    source: Path,
    scenarios: Path,
    plots: Path | None,
    candidate: str,
    baseline: str | None,
    generated_at: str | None = None,
    avsb_version: str | None = None,
) -> Path:
    """Ingest one candidate and return the directory that was written."""
    if track != "a":
        raise IngestRefused("only track a is ingested from AVSB runs")

    planner_dir = Path(source) / candidate
    if not planner_dir.is_dir():
        raise IngestRefused(f"no results for candidate {candidate!r} under {source}")
    result_files = sorted(planner_dir.glob("*.result.json"))
    if not result_files:
        raise IngestRefused(f"no *.result.json files under {planner_dir}")

    stamp = generated_at or newest_mtime_utc(result_files)
    record = check_preregistration(Path(root), suite, stamp)

    out_dir = Path(root) / "runs" / suite / candidate
    scenarios_map = avsb.load_scenarios(Path(scenarios))
    results = avsb.read_planner_results(
        Path(source),
        scenarios_map,
        planner=candidate,
        suite=suite,
        plots_root=Path(plots) if plots else None,
        thumbs_dir=Path(root) / "runs" / suite / "thumbs",
    )

    gate_file = f"gates/track_{track}.yaml"
    manifest = avsb.build_manifest(
        suite=suite,
        candidate=candidate,
        baseline=baseline,
        generated_at=stamp,
        preregistered=suite != DEMO_SUITE and record is not None,
        gate_file=gate_file,
        sha256=avsb.gate_file_sha256(Path(root) / gate_file),
        n_results=len(results),
        avsb_version=avsb_version,
        gate_version=__version__,
    )
    avsb.write_candidate(out_dir, results, manifest)
    return out_dir


def newest_mtime_utc(paths: list[Path]) -> str:
    """Return the newest file modification time in the list, UTC with a `Z`."""
    stamps = [p.stat().st_mtime for p in paths if p.is_file()]
    moment = datetime.fromtimestamp(max(stamps), tz=timezone.utc)
    return avsb.utc_z(moment)


def _cmd(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        out_dir = ingest(
            root,
            track=args.track,
            suite=args.suite,
            source=Path(args.from_),
            scenarios=Path(args.scenarios),
            plots=Path(args.plots) if args.plots else None,
            candidate=args.candidate,
            baseline=args.baseline,
            generated_at=args.generated_at,
            avsb_version=args.avsb_version,
        )
    except IngestRefused as exc:
        print(f"ingest: refused, {exc}", file=sys.stderr)
        return 2
    print(f"ingest: wrote {out_dir.relative_to(root).as_posix()}")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add the `ingest` subcommand to the CLI root."""
    parser = subparsers.add_parser("ingest", help="Ingest an AVSB run directory into runs/")
    parser.add_argument("--track", choices=["a", "b"], default="a")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--from", dest="from_", required=True, help="AVSB runs directory")
    parser.add_argument("--scenarios", required=True, help="Scenario YAML root")
    parser.add_argument("--plots", default=None, help="BEV plot directory")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--generated-at", dest="generated_at", default=None)
    parser.add_argument("--avsb-version", dest="avsb_version", default=None)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.set_defaults(func=_cmd)
