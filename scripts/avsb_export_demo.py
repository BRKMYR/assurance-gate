"""Export the existing AVSB `core` results into `runs/demo`.

See docs/ARCHITECTURE.md section 7.1. The demo suite carries
`preregistered: false` because the gates were written after those runs, and the
dashboard says so on every page. Run it from the repository root:

    .venv/bin/python scripts/avsb_export_demo.py
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from gate import __version__
from gate.adapters import avsb

DEFAULT_AVSB = Path.home() / "src/github.com/BRKMYR/av-safety-benchmark"
CANDIDATES: tuple[tuple[str, str | None], ...] = (
    ("cautious_idm", "idm"),
    ("idm", None),
    ("constant_velocity", "idm"),
)
SUITE = "demo"


def export(root: Path, avsb_root: Path, avsb_version: str | None) -> list[Path]:
    """Write the demo suite and return the directories that were written."""
    results_root = avsb_root / "artifacts/core"
    plots_root = avsb_root / "artifacts/reports/core/plots"
    scenarios = avsb.load_scenarios(results_root)
    gate_file = "gates/track_a.yaml"
    sha256 = avsb.gate_file_sha256(root / gate_file)

    all_files = sorted(results_root.rglob("*.result.json"))
    first_run_at = avsb.oldest_mtime_utc(all_files) or avsb.utc_z(datetime.now(timezone.utc))

    written: list[Path] = []
    for candidate, baseline in CANDIDATES:
        results = avsb.read_planner_results(
            results_root,
            scenarios,
            planner=candidate,
            suite=SUITE,
            plots_root=plots_root,
            thumbs_dir=root / "runs" / SUITE / "thumbs",
        )
        manifest = avsb.build_manifest(
            suite=SUITE,
            candidate=candidate,
            baseline=baseline,
            generated_at=first_run_at,
            preregistered=False,
            gate_file=gate_file,
            sha256=sha256,
            n_results=len(results),
            gate_published_at=None,
            avsb_version=avsb_version,
            gate_version=__version__,
            notes="Demo data. Gates were written after these runs.",
        )
        out_dir = root / "runs" / SUITE / candidate
        avsb.write_candidate(out_dir, results, manifest)
        written.append(out_dir)
        print(f"export: {candidate} {len(results)} results into {out_dir.relative_to(root).as_posix()}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the AVSB core suite into runs/demo.")
    parser.add_argument("--avsb", default=str(DEFAULT_AVSB), help="AVSB checkout")
    parser.add_argument("--root", default=".", help="assurance-gate repository root")
    parser.add_argument("--avsb-version", dest="avsb_version", default="0.1.0")
    args = parser.parse_args(argv)
    export(Path(args.root).resolve(), Path(args.avsb).expanduser(), args.avsb_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
