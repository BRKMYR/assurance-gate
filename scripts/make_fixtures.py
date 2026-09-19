"""Regenerate `tests/fixtures` deterministically. Spec section 13.

Source is the private AVSB checkout. The script copies six raw results with
their `trajectory_log` still in place, the matching scenario YAML and two BEV
plots, then writes a small runs tree in the layout of spec 7.1 and the golden
`data.json`. Run it only when the fixtures need to change.

Usage: .venv/bin/python scripts/make_fixtures.py [--avsb <checkout>]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from gate.build import build_site, dumps
from gate.gates import sha256_file
from gate.schema import SCHEMA_VERSION, Manifest, Metrics, Result

REPO = Path(__file__).resolve().parents[1]
DEFAULT_AVSB = Path.home() / "src/github.com/BRKMYR/av-safety-benchmark"
FIXTURES = REPO / "tests/fixtures"
AVSB_FIXTURES = FIXTURES / "avsb"
RUNS_FIXTURE = FIXTURES / "runs_fixture"
SUITE = "fixture"
GENERATED_AT = "2026-09-19T00:00:00Z"

SELECTION: dict[str, list[tuple[str, str]]] = {
    "cautious_idm": [
        ("cut_in", "core-cutin-0010"),
        ("hard_brake", "core-hardbrake-0007"),
        ("ped_occluded", "core-ped-0001"),
        ("weather_ramp", "core-weather-0008"),
    ],
    "idm": [
        ("ped_occluded", "core-ped-0001"),
        ("ped_occluded", "core-ped-0009"),
    ],
}
PLOTS = [
    "bev_ped_occluded_cautious_idm_core-ped-0001.png",
    "bev_ped_occluded_idm_core-ped-0001.png",
]
PUBLIC_METRICS = set(Metrics.model_fields)


def copy_sources(avsb: Path) -> None:
    """Copy the raw AVSB inputs into `tests/fixtures/avsb/`."""
    if AVSB_FIXTURES.exists():
        shutil.rmtree(AVSB_FIXTURES)
    for planner, items in SELECTION.items():
        (AVSB_FIXTURES / planner).mkdir(parents=True, exist_ok=True)
        for family, scenario_id in items:
            shutil.copyfile(
                avsb / "artifacts/core" / planner / f"{scenario_id}.result.json",
                AVSB_FIXTURES / planner / f"{scenario_id}.result.json",
            )
            (AVSB_FIXTURES / family).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                avsb / "artifacts/core" / family / f"{scenario_id}.yaml",
                AVSB_FIXTURES / family / f"{scenario_id}.yaml",
            )
    (AVSB_FIXTURES / "plots").mkdir(parents=True, exist_ok=True)
    for name in PLOTS:
        shutil.copyfile(avsb / "artifacts/reports/core/plots" / name, AVSB_FIXTURES / "plots" / name)


def to_result(raw: dict[str, Any], scenario: dict[str, Any], planner: str, thumbnail: str | None) -> Result:
    """Turn one raw AVSB result plus its scenario YAML into a public Result."""
    metrics = {k: v for k, v in (raw.get("metrics") or {}).items() if k in PUBLIC_METRICS}
    parameters = {k: (None if v is None else float(v)) for k, v in (scenario.get("parameters") or {}).items()}
    return Result(
        scenario_id=raw["scenario_id"],
        family=raw["family"],
        planner=planner,
        suite=SUITE,
        duration_s=raw.get("duration_s"),
        n_steps=raw.get("n_steps"),
        score=raw.get("score"),
        severity_tier=raw.get("severity_tier"),
        metrics=Metrics(**metrics),
        parameters=parameters,
        description=str(scenario.get("description", "")),
        thumbnail=thumbnail,
    )


def write_runs() -> None:
    """Write the fixture runs tree in the layout of spec 7.1."""
    if RUNS_FIXTURE.exists():
        shutil.rmtree(RUNS_FIXTURE)
    suite_dir = RUNS_FIXTURE / SUITE
    thumbs = suite_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    plot_names = {p.name for p in (AVSB_FIXTURES / "plots").glob("*.png")}
    gate_sha = sha256_file(REPO / "gates/track_a.yaml")

    for planner, items in SELECTION.items():
        results = []
        for family, scenario_id in items:
            raw = json.loads((AVSB_FIXTURES / planner / f"{scenario_id}.result.json").read_text(encoding="utf-8"))
            scenario = yaml.safe_load((AVSB_FIXTURES / family / f"{scenario_id}.yaml").read_text(encoding="utf-8"))
            plot = f"bev_{family}_{planner}_{scenario_id}.png"
            thumbnail = None
            if plot in plot_names:
                shutil.copyfile(AVSB_FIXTURES / "plots" / plot, thumbs / f"{family}_{planner}_{scenario_id}.png")
                thumbnail = f"thumbs/{family}_{planner}_{scenario_id}.png"
            results.append(to_result(raw, scenario, planner, thumbnail))
        results.sort(key=lambda r: r.scenario_id)
        candidate_dir = suite_dir / planner
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "results.json").write_text(dumps([r.model_dump() for r in results]), encoding="utf-8")
        manifest = Manifest(
            schema_version=SCHEMA_VERSION,
            run_id=f"{SUITE}-{planner}-20260919T000000Z",
            suite=SUITE,
            track="a",
            candidate=planner,
            baseline="idm" if planner != "idm" else None,
            generated_at=GENERATED_AT,
            preregistered=False,
            gate_file="gates/track_a.yaml",
            gate_file_sha256=gate_sha,
            gate_published_at=None,
            seed=int(gate_sha[:8], 16),
            n_results=len(results),
            notes="",
        )
        (candidate_dir / "manifest.json").write_text(dumps(manifest.model_dump()), encoding="utf-8")


def write_manifests() -> None:
    """Write one Track A and one Track B manifest into `tests/fixtures/manifests/`."""
    target = FIXTURES / "manifests"
    target.mkdir(parents=True, exist_ok=True)
    gate_a = sha256_file(REPO / "gates/track_a.yaml")
    gate_b = sha256_file(REPO / "gates/track_b.yaml")
    manifest_a = Manifest(
        run_id="holdout-cautious_idm-20260921T101500Z",
        suite="holdout",
        track="a",
        candidate="cautious_idm",
        baseline="idm",
        generated_at="2026-09-21T10:15:00Z",
        preregistered=True,
        gate_file="gates/track_a.yaml",
        gate_file_sha256=gate_a,
        seed=int(gate_a[:8], 16),
        n_results=60,
    )
    manifest_b = Manifest(
        run_id="holdout-qwen25-7b-20260921T120000Z",
        suite="holdout",
        track="b",
        candidate="Qwen/Qwen2.5-7B-Instruct",
        baseline="Qwen/Qwen2.5-7B-Instruct",
        generated_at="2026-09-21T12:00:00Z",
        preregistered=True,
        gate_file="gates/track_b.yaml",
        gate_file_sha256=gate_b,
        seed=0,
        n_results=450,
    )
    (target / "track_a.json").write_text(dumps(manifest_a.model_dump()), encoding="utf-8")
    (target / "track_b.json").write_text(dumps(manifest_b.model_dump()), encoding="utf-8")


def write_golden(out: Path) -> None:
    """Build from the fixture runs and store the golden `data.json`."""
    build_site(
        runs_root=RUNS_FIXTURE,
        out=out,
        strings_path=None,
        required_path=out / "none.txt",
        bins_path=REPO / "configs/coverage_bins.yaml",
        gate_files={"a": REPO / "gates/track_a.yaml", "b": REPO / "gates/track_b.yaml"},
    )
    shutil.copyfile(out / "data.json", FIXTURES / "data.json")


def main(argv: list[str] | None = None) -> int:
    """Regenerate every fixture."""
    parser = argparse.ArgumentParser(description="Regenerate tests/fixtures.")
    parser.add_argument("--avsb", default=str(DEFAULT_AVSB), help="AVSB checkout.")
    parser.add_argument("--skip-copy", action="store_true", help="Reuse the copied AVSB inputs.")
    args = parser.parse_args(argv)
    if not args.skip_copy:
        copy_sources(Path(args.avsb))
    write_runs()
    write_manifests()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        write_golden(Path(tmp))
    print("fixtures written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
