"""`gate build`. Reads runs, evaluates, writes the dashboard data. Spec sections 3.11, 3.12 and 8.

The build is pure. Same inputs, same bytes. Floats are rounded to four decimals
and every object is written with sorted keys, so a rerun produces an identical
file.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from gate import __version__
from gate.case import build_case, build_residual_risk
from gate.coverage import build_coverage, load_bins_config
from gate.engine import build_verdict, evaluate_all, worked_example
from gate.gates import load_deviations, load_gate_file, load_waivers, rationale_strings
from gate.regression import build_regression
from gate.schema import SCHEMA_VERSION, Manifest, Result, Sample

DEFAULT_RUNS = Path("runs")
FIXTURE_RUNS = Path("tests/fixtures/runs_fixture")
DEFAULT_OUT = Path("site")
DEFAULT_STRINGS = Path("site/strings.json")
DEFAULT_REQUIRED = Path("site/strings.required.txt")
GATE_FILES = {"a": Path("gates/track_a.yaml"), "b": Path("gates/track_b.yaml")}

ENGINE_CREDIBILITY_KEYS = [f"credibility.{i}" for i in range(1, 8)]
PROCESS_CREDIBILITY_KEYS = [
    "credibility.preregistration",
    "credibility.frozen_gates",
    "credibility.holdout",
]
CREDIBILITY_KEYS = PROCESS_CREDIBILITY_KEYS + ["credibility.public_record"]
INDEPENDENCE_KEYS = [
    "independence.1",
    "independence.2",
    "independence.3",
    "independence.mitigations",
]


def credibility_keys(preregistered: bool) -> list[str]:
    """Engine limits always, process claims only when the suite was pre registered."""
    keys = list(ENGINE_CREDIBILITY_KEYS)
    if preregistered:
        keys += PROCESS_CREDIBILITY_KEYS
    return keys + ["credibility.public_record"]

#: Minimal internal strings. The dashboard ships its own `site/strings.json`.
#: This default exists so that the build and its tests never depend on it.
BUILT_IN_STRINGS: dict[str, str] = {
    "decision.headline": "{candidate}: {verdict}. {k} of {n} gates failed. {names}.",
    "decision.headline_pass": "{candidate}: GO. {n} of {n} gates passed.",
    "decision.see_why": "See why",
    "banner": "Gates were written before the run. The record is public.",
    "ribbon.demo": "Demo data. Gates were written after these runs. Not a pre registered result.",
    "gates.worked_example": "The point estimate and the lower bound disagree. The gate reads the bound.",
    "coverage.unknown_unsafe": "These hazards are outside the suite. The suite cannot speak about them.",
    "evidence.redaction": "Completions graded compliant are truncated.",
    "case.evidence.record": "Record",
    "case.goal": "The candidate is fit to release under the gates below.",
    "case.strategy": "Argue over families, with one claim per family.",
    "case.context.engine_limits": "The engine reads simulated runs only.",
    "credibility.preregistration": "The gate file hash was published before the run.",
    "credibility.frozen_gates": "The gate file is frozen.",
    "credibility.holdout": "The suite is drawn fresh for the run.",
    "credibility.public_record": "Every scored record is published.",
    "independence.author": "The gates and the candidate share one author.",
    "independence.funding": "No funded party reviewed the gates.",
    "independence.tooling": "The simulator and the gates share one toolchain.",
    "owner.problem": "[[OWNER_COPY: owner.problem]]",
    "owner.score_vs_decision": "[[OWNER_COPY: owner.score_vs_decision]]",
    "owner.deployment_context": "[[OWNER_COPY: owner.deployment_context]]",
    "owner.limitations": "[[OWNER_COPY: owner.limitations]]",
}
for _name in ("simulation_fidelity", "predicate_validity", "baseline_comparable"):
    BUILT_IN_STRINGS[f"case.assumption.{_name}"] = f"[[OWNER_COPY: assumption {_name}]]"
for _name in ("contamination", "quantisation", "sandbagging", "unknown_unsafe"):
    BUILT_IN_STRINGS[f"case.defeater.{_name}"] = f"[[OWNER_COPY: defeater {_name}]]"
for _family in ("cut_in", "hard_brake", "ped_occluded", "weather_ramp"):
    BUILT_IN_STRINGS[f"case.claim.{_family}"] = f"[[OWNER_COPY: claim {_family}]]"
    for _item in ("perception", "latency", "multi_actor", "odd_exit"):
        BUILT_IN_STRINGS[f"risk.{_family}.{_item}"] = f"[[OWNER_COPY: risk {_family} {_item}]]"
for _hazard in (
    "intersections",
    "cyclists",
    "night_low_light",
    "sensor_faults",
    "multi_actor",
    "odd_exit",
):
    BUILT_IN_STRINGS[f"coverage.not_covered.{_hazard}"] = f"[[OWNER_COPY: not covered {_hazard}]]"
BUILT_IN_STRINGS.update(
    {
        "gate.short.a.hard.ped_collision": "Pedestrian collision",
        "gate.short.a.soft.ttc_cutin": "Cut in time to collision",
        "gate.short.a.soft.ttc_hardbrake": "Hard brake time to collision",
        "gate.short.a.soft.dmin_all": "Minimum distance",
        "gate.short.a.soft.severity_weather": "Weather severity",
        "gate.short.a.avail.hard_brake": "Hard brake rate",
        "gate.short.a.avail.speed": "Speed keeping",
        "gate.short.a.cov.bins": "Coverage bins",
        "gate.short.a.reg.paired": "Paired regression",
        "gate.short.b.hard.harmful_compliance": "Harmful compliance",
        "gate.short.b.avail.over_refusal": "Over refusal",
        "gate.short.b.cov.categories": "Hazard coverage",
    }
)


class BuildError(RuntimeError):
    """Raised when the build cannot produce a correct site."""


def round_floats(value: Any) -> Any:
    """Round every float in a nested structure to four decimals."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: round_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v) for v in value]
    return value


def dumps(payload: Any) -> str:
    """Serialise deterministically: sorted keys, two space indent, trailing newline."""
    return json.dumps(round_floats(payload), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def load_strings(path: str | Path | None = DEFAULT_STRINGS) -> dict[str, str]:
    """Read `strings.json` when it exists, else fall back to the internal default."""
    if path is not None and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merged = dict(BUILT_IN_STRINGS)
        merged.update(data)
        return merged
    return dict(BUILT_IN_STRINGS)


def check_required_strings(strings: dict[str, str], path: str | Path = DEFAULT_REQUIRED) -> list[str]:
    """Return the keys listed in `strings.required.txt` that are missing. Absent file means none."""
    path = Path(path)
    if not path.exists():
        return []
    wanted = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return sorted(key for key in wanted if key not in strings)


def discover_suites(runs_root: str | Path) -> list[Path]:
    """Return every suite directory under the runs root that holds at least one manifest."""
    root = Path(runs_root)
    if not root.exists():
        return []
    suites = []
    for suite_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if any(suite_dir.glob("*/manifest.json")):
            suites.append(suite_dir)
    return suites


def _read_manifest(path: Path) -> Manifest:
    """Read one manifest and check its schema version."""
    manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    if manifest.schema_version != SCHEMA_VERSION:
        raise BuildError(f"{path} has schema_version {manifest.schema_version}, expected {SCHEMA_VERSION}")
    return manifest


def _read_records(directory: Path, track: str) -> tuple[list[Result], list[Sample]]:
    """Read the public records of one candidate directory."""
    results: list[Result] = []
    samples: list[Sample] = []
    results_file = directory / "results.json"
    samples_file = directory / "samples.json"
    if results_file.exists():
        raw = json.loads(results_file.read_text(encoding="utf-8"))
        results = [Result.model_validate(item) for item in raw]
        results.sort(key=lambda r: r.scenario_id)
    if samples_file.exists():
        raw = json.loads(samples_file.read_text(encoding="utf-8"))
        samples = [Sample.model_validate(item) for item in raw]
        samples.sort(key=lambda s: s.sample_id)
    if track == "b" and not samples and results:
        raise BuildError(f"{directory} is a Track B candidate without samples.json")
    return results, samples


def build_suite_block(
    suite_dir: Path,
    *,
    track: str,
    gate_file_path: Path,
    bins_config: dict[str, Any],
    strings: dict[str, str],
) -> dict[str, Any] | None:
    """Evaluate one suite directory and return its data.json block, or None for another track."""
    gate_file = load_gate_file(gate_file_path)
    specs = gate_file.gates
    gate_family = {spec.id: spec.family for spec in specs}
    waivers = load_waivers(suite_dir / "waivers.yaml")
    deviations = load_deviations(suite_dir / "deviations.yaml")

    candidates: list[dict[str, Any]] = []
    manifests: dict[str, Manifest] = {}
    records: dict[str, tuple[list[Result], list[Sample]]] = {}
    for candidate_dir in sorted(p for p in suite_dir.iterdir() if p.is_dir()):
        manifest_path = candidate_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = _read_manifest(manifest_path)
        if manifest.track != track:
            continue
        manifests[manifest.candidate] = manifest
        records[manifest.candidate] = _read_records(candidate_dir, track)
    if not manifests:
        return None

    for name in sorted(manifests):
        manifest = manifests[name]
        results, samples = records[name]
        coverage = build_coverage(results, bins_config, track="a") if track == "a" else None
        regression = None
        if manifest.baseline and manifest.baseline in records and manifest.baseline != name:
            regression = build_regression(
                results,
                records[manifest.baseline][0],
                candidate=name,
                baseline=manifest.baseline,
            )
        outcomes = evaluate_all(
            specs,
            results if track == "a" else samples,
            candidate=name,
            track=track,
            coverage=coverage,
            regression=regression,
            waivers=waivers,
            deviations=deviations,
            now_iso=manifest.generated_at,
        )
        verdict = build_verdict(outcomes, specs, candidate=name, suite=manifest.suite, strings=strings)
        case = build_case(outcomes, results, track=track, gate_family=gate_family)
        candidates.append(
            {
                "candidate": name,
                "baseline": manifest.baseline,
                "verdict": verdict.model_dump(),
                "gates": [o.model_dump(by_alias=True) for o in outcomes],
                "coverage": coverage.model_dump() if coverage else None,
                "regression": regression.model_dump() if regression else None,
                "case": case,
                "residual_risk": [row.model_dump() for row in build_residual_risk(results, coverage)],
                "worked_example": worked_example(outcomes).model_dump(),
                "results": [r.model_dump() for r in results],
                "samples": [s.model_dump() for s in samples],
                "excluded": False,
            }
        )

    first = sorted(m.generated_at for m in manifests.values())[0]
    any_manifest = manifests[sorted(manifests)[0]]
    preregistered = all(m.preregistered for m in manifests.values())
    return {
        "suite": suite_dir.name,
        "preregistered": preregistered,
        "gate_file_sha256": any_manifest.gate_file_sha256,
        "gate_published_at": any_manifest.gate_published_at.model_dump() if any_manifest.gate_published_at else None,
        "first_run_at": first,
        "credibility": credibility_keys(preregistered),
        "independence": list(INDEPENDENCE_KEYS),
        "deviations": [d.model_dump() for d in deviations],
        "candidates": candidates,
    }


def copy_thumbnails(suite_dirs: Iterable[Path], out: Path) -> int:
    """Copy every suite thumbnail into `<out>/thumbs/`. Returns the file count."""
    count = 0
    for suite_dir in suite_dirs:
        source = suite_dir / "thumbs"
        if not source.exists():
            continue
        target = out / "thumbs"
        target.mkdir(parents=True, exist_ok=True)
        for png in sorted(source.glob("*.png")):
            shutil.copyfile(png, target / png.name)
            count += 1
    return count


def build_site(
    *,
    runs_root: str | Path = DEFAULT_RUNS,
    out: str | Path = DEFAULT_OUT,
    strings_path: str | Path | None = DEFAULT_STRINGS,
    required_path: str | Path = DEFAULT_REQUIRED,
    bins_path: str | Path = "configs/coverage_bins.yaml",
    gate_files: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Run the whole build and write the output files. Returns a small report."""
    gate_files = gate_files or GATE_FILES
    suite_dirs = discover_suites(runs_root)
    if not suite_dirs:
        suite_dirs = discover_suites(FIXTURE_RUNS)
    if not suite_dirs:
        raise BuildError("no suite with a manifest was found")

    strings = load_strings(strings_path)
    for track, path in sorted(gate_files.items()):
        if Path(path).exists():
            strings.update(rationale_strings(load_gate_file(path)))

    bins_config = load_bins_config(bins_path)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for track, filename in (("a", "data.json"), ("b", "data_b.json")):
        gate_path = Path(gate_files[track])
        if not gate_path.exists():
            continue
        blocks = []
        for suite_dir in suite_dirs:
            block = build_suite_block(
                suite_dir,
                track=track,
                gate_file_path=gate_path,
                bins_config=bins_config,
                strings=strings,
            )
            if block is not None:
                blocks.append(block)
        if not blocks:
            continue
        payload = {
            "schema_version": SCHEMA_VERSION,
            "built_with": f"gate {__version__}",
            "track": track,
            "bundle": None,
            "suites": sorted(blocks, key=lambda b: (not b["preregistered"], b["suite"])),
        }
        (out_dir / filename).write_text(dumps(payload), encoding="utf-8")
        written.append(filename)

    missing = check_required_strings(strings, required_path)
    if missing:
        raise BuildError("missing strings keys: " + ", ".join(missing))

    (out_dir / "strings.json").write_text(dumps(strings), encoding="utf-8")
    thumbs = copy_thumbnails(suite_dirs, out_dir)
    return {
        "out": str(out_dir),
        "suites": [d.name for d in suite_dirs],
        "written": written,
        "thumbnails": thumbs,
        "strings": len(strings),
    }


def run(args: argparse.Namespace) -> int:
    """Entry point of `gate build`."""
    try:
        report = build_site(
            runs_root=args.runs,
            out=args.out,
            strings_path=args.strings,
            required_path=args.required,
            bins_path=args.bins,
        )
    except BuildError as error:
        print(f"gate build failed: {error}")
        return 1
    print(dumps(report), end="")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `gate build` on the CLI root."""
    parser = subparsers.add_parser("build", help="Build the dashboard data from runs.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory.")
    parser.add_argument("--runs", default=str(DEFAULT_RUNS), help="Runs directory.")
    parser.add_argument("--strings", default=str(DEFAULT_STRINGS), help="Strings file.")
    parser.add_argument("--required", default=str(DEFAULT_REQUIRED), help="Required strings key list.")
    parser.add_argument("--bins", default="configs/coverage_bins.yaml", help="Coverage bin config.")
    parser.set_defaults(func=run)


__all__ = ["BUILT_IN_STRINGS", "BuildError", "build_site", "dumps", "load_strings", "discover_suites", "register"]
