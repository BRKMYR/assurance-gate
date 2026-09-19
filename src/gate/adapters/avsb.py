"""AVSB result and scenario card adapter. See docs/ARCHITECTURE.md section 7.1.

Input is the directory layout AVSB writes: `<root>/<planner>/<scenario_id>.result.json`
for results, `<root>/<family>/<scenario_id>.yaml` for scenario definitions and
`<plots>/bev_<family>_<planner>_<scenario_id>.png` for thumbnails. Output is a
list of `Result` records plus a `Manifest`, both from schema.py.

The adapter removes `trajectory_log` by construction: it copies named fields out
of the raw dictionary instead of copying the dictionary, so a private field can
never reach an output file (AC-12).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from gate.schema import SCHEMA_VERSION, Manifest, Metrics, PublishedAt, Result, ToolVersions

ZERO_SHA = "0" * 64

#: Parameter names per family, in the order of docs/ARCHITECTURE.md section 3.2.
FAMILY_PARAMETERS: dict[str, tuple[str, ...]] = {
    "cut_in": ("ego_speed_mps", "initial_gap_m", "speed_delta_mps", "trigger_gap_m", "lateral_speed_mps"),
    "ped_occluded": ("ego_speed_mps", "occluder_x_m", "ped_speed_mps", "trigger_offset_m"),
    "weather_ramp": ("ego_speed_mps", "visibility_end_m", "friction_end"),
    "hard_brake": ("ego_speed_mps", "initial_gap_m", "lead_speed_delta_mps", "brake_decel_mps2"),
}

METRIC_FIELDS: tuple[str, ...] = tuple(Metrics.model_fields)


# --- small helpers ----------------------------------------------------------


def _num(value: Any) -> float | None:
    """Return `value` as a float, or None when it is missing or not numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _actor(scen: dict[str, Any], *, kind: str | None = None, actor_id: str | None = None) -> dict[str, Any] | None:
    """Return the first actor matching `kind` or `actor_id`, else None."""
    for actor in scen.get("actors") or []:
        if not isinstance(actor, dict):
            continue
        if actor_id is not None and actor.get("actor_id") == actor_id:
            return actor
        if kind is not None and actor.get("kind") == kind:
            return actor
    return None


def _non_ego_actor(scen: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first actor that is not the ego vehicle."""
    for actor in scen.get("actors") or []:
        if isinstance(actor, dict) and actor.get("actor_id") != "ego":
            return actor
    return None


def _initial(actor: dict[str, Any] | None, field: str) -> float | None:
    if not actor:
        return None
    return _num((actor.get("initial") or {}).get(field))


def _phases(actor: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not actor:
        return []
    return [p for p in (actor.get("phases") or []) if isinstance(p, dict)]


def _trigger_value(phase: dict[str, Any], field: str) -> float | None:
    return _num((phase.get("trigger") or {}).get(field))


# --- parameter recovery -----------------------------------------------------


def recover_parameters(scen: dict[str, Any]) -> dict[str, float | None]:
    """Recover the family draw parameters from a scenario YAML dictionary.

    Every formula is the one written in docs/ARCHITECTURE.md section 3.2. A
    parameter the adapter cannot derive from the actor and environment blocks
    falls back to the YAML `parameters` block, and is None when that is absent
    too. The scenario then counts toward no coverage bin.
    """
    family = str(scen.get("family") or "")
    names = FAMILY_PARAMETERS.get(family, ())
    declared = scen.get("parameters") if isinstance(scen.get("parameters"), dict) else {}
    ego = scen.get("ego") if isinstance(scen.get("ego"), dict) else {}
    env = scen.get("environment") if isinstance(scen.get("environment"), dict) else {}

    ego_speed = _num((ego.get("initial") or {}).get("speed_mps"))
    derived: dict[str, float | None] = {"ego_speed_mps": ego_speed}

    if family == "cut_in":
        cutter = _actor(scen, actor_id="cutter") or _non_ego_actor(scen)
        cutter_x = _initial(cutter, "x_m")
        ego_x = _num((ego.get("initial") or {}).get("x_m"))
        cutter_speed = _initial(cutter, "speed_mps")
        derived["initial_gap_m"] = None if cutter_x is None or ego_x is None else cutter_x - ego_x
        derived["speed_delta_mps"] = None if cutter_speed is None or ego_speed is None else cutter_speed - ego_speed
        derived["trigger_gap_m"] = next(
            (v for p in _phases(cutter) if (v := _trigger_value(p, "gap_m")) is not None), None
        )
        derived["lateral_speed_mps"] = next(
            (v for p in _phases(cutter) if (v := _num(p.get("lateral_speed_mps"))) not in (None, 0.0)), None
        )
    elif family == "ped_occluded":
        occluder = _actor(scen, actor_id="occluder") or _actor(scen, kind="static")
        ped = _actor(scen, actor_id="pedestrian") or _actor(scen, kind="pedestrian")
        occluder_x = _initial(occluder, "x_m")
        derived["occluder_x_m"] = occluder_x
        crossing = next(
            (p for p in _phases(ped) if _num(p.get("lateral_speed_mps")) not in (None, 0.0)), None
        )
        derived["ped_speed_mps"] = None if crossing is None else _num(crossing.get("lateral_speed_mps"))
        trigger_x = None if crossing is None else _trigger_value(crossing, "ego_x_m")
        derived["trigger_offset_m"] = (
            None if occluder_x is None or trigger_x is None else occluder_x - trigger_x
        )
    elif family == "weather_ramp":
        derived["visibility_end_m"] = _num(env.get("visibility_end_m"))
        derived["friction_end"] = _num(env.get("friction_end"))
    elif family == "hard_brake":
        lead = _actor(scen, actor_id="lead") or _non_ego_actor(scen)
        lead_x = _initial(lead, "x_m")
        ego_x = _num((ego.get("initial") or {}).get("x_m"))
        lead_speed = _initial(lead, "speed_mps")
        derived["initial_gap_m"] = None if lead_x is None or ego_x is None else lead_x - ego_x
        derived["lead_speed_delta_mps"] = None if lead_speed is None or ego_speed is None else ego_speed - lead_speed
        brake = next(
            (v for p in _phases(lead) if (v := _num(p.get("accel_mps2"))) not in (None, 0.0)), None
        )
        derived["brake_decel_mps2"] = None if brake is None else abs(brake)

    out: dict[str, float | None] = {}
    for name in names:
        value = derived.get(name)
        if value is None:
            value = _num(declared.get(name))
            if value is not None and name == "brake_decel_mps2":
                value = abs(value)
        out[name] = None if value is None else round(value, 4)
    return out


# --- result building --------------------------------------------------------


def load_scenarios(scenarios_root: Path) -> dict[str, dict[str, Any]]:
    """Read every `<family>/<scenario_id>.yaml` under `scenarios_root`.

    Returns a mapping of scenario id to the parsed YAML dictionary. Directories
    that hold planner results rather than scenario definitions are skipped
    because their files do not end in `.yaml`.
    """
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(scenarios_root).rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("scenario_id"):
            scenarios[str(data["scenario_id"])] = data
    return scenarios


def build_result(
    raw: dict[str, Any],
    scen: dict[str, Any] | None,
    *,
    suite: str,
    thumbnail: str | None = None,
) -> Result:
    """Build one public `Result` from a raw AVSB result dictionary.

    Only named fields are copied. `trajectory_log` and any other private key in
    `raw` is dropped, and `mean_speed_ratio` stays None when the source is AVSB
    schema 1.0.
    """
    raw_metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    metrics = Metrics(**{k: raw_metrics.get(k) for k in METRIC_FIELDS if k in raw_metrics})
    scen = scen or {}
    return Result(
        scenario_id=str(raw.get("scenario_id", "")),
        family=str(raw.get("family", scen.get("family", ""))),
        planner=str(raw.get("planner", "")),
        suite=suite,
        duration_s=_num(raw.get("duration_s")),
        n_steps=raw.get("n_steps"),
        score=_num(raw.get("score")),
        severity_tier=raw.get("severity_tier"),
        metrics=metrics,
        parameters=recover_parameters(scen) if scen else {},
        description=str(scen.get("description") or ""),
        thumbnail=thumbnail,
    )


def thumbnail_name(family: str, planner: str, scenario_id: str) -> str:
    """Return the thumbnail file name for one result."""
    return f"{family}_{planner}_{scenario_id}.png"


def copy_thumbnail(plots_root: Path | None, result: Result, thumbs_dir: Path) -> str | None:
    """Copy the BEV plot for `result` into `thumbs_dir` and return its relative path.

    Returns None when no plot exists for that scenario and planner.
    """
    if plots_root is None:
        return None
    source = Path(plots_root) / f"bev_{thumbnail_name(result.family, result.planner, result.scenario_id)}"
    if not source.is_file():
        return None
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    name = thumbnail_name(result.family, result.planner, result.scenario_id)
    shutil.copyfile(source, thumbs_dir / name)
    return f"thumbs/{name}"


def read_planner_results(
    results_root: Path,
    scenarios: dict[str, dict[str, Any]],
    *,
    planner: str,
    suite: str,
    plots_root: Path | None = None,
    thumbs_dir: Path | None = None,
) -> list[Result]:
    """Read every `*.result.json` for one planner, sorted by scenario id."""
    planner_dir = Path(results_root) / planner
    results: list[Result] = []
    for path in sorted(planner_dir.glob("*.result.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = build_result(raw, scenarios.get(str(raw.get("scenario_id"))), suite=suite)
        if thumbs_dir is not None:
            result = result.model_copy(update={"thumbnail": copy_thumbnail(plots_root, result, thumbs_dir)})
        results.append(result)
    results.sort(key=lambda r: r.scenario_id)
    return results


# --- manifest and writing ---------------------------------------------------


def gate_file_sha256(gate_file: Path | str) -> str:
    """Return the SHA 256 of the gate file bytes, or 64 zeros when it is absent.

    Computed lazily at call time so that ingest works before the gate file lands.
    """
    path = Path(gate_file)
    if not path.is_file():
        return ZERO_SHA
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_z(moment: datetime) -> str:
    """Format a datetime as ISO 8601 UTC with a `Z` suffix and second precision."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def oldest_mtime_utc(paths: list[Path]) -> str | None:
    """Return the oldest file modification time in the list, as UTC with a `Z`."""
    stamps = [p.stat().st_mtime for p in paths if p.is_file()]
    if not stamps:
        return None
    return utc_z(datetime.fromtimestamp(min(stamps), tz=timezone.utc))


def seed_from_hash(sha256: str) -> int:
    """Track A seed: the first eight hex characters of the gate file hash."""
    try:
        return int(sha256[:8], 16)
    except ValueError:
        return 0


def build_manifest(
    *,
    suite: str,
    candidate: str,
    baseline: str | None,
    generated_at: str,
    preregistered: bool,
    gate_file: str,
    sha256: str,
    n_results: int,
    gate_published_at: PublishedAt | None = None,
    avsb_version: str | None = None,
    gate_version: str | None = None,
    notes: str = "",
) -> Manifest:
    """Build the Track A manifest of docs/ARCHITECTURE.md section 3.1."""
    run_id = f"{suite}-{candidate}-{generated_at.replace('-', '').replace(':', '')}"
    return Manifest(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        suite=suite,
        track="a",
        candidate=candidate,
        baseline=baseline,
        generated_at=generated_at,
        preregistered=preregistered,
        gate_file=gate_file,
        gate_file_sha256=sha256,
        gate_published_at=gate_published_at,
        seed=seed_from_hash(sha256),
        tools=ToolVersions(avsb=avsb_version, gate=gate_version),
        n_results=n_results,
        notes=notes,
    )


def write_json(path: Path, payload: Any) -> Path:
    """Write deterministic JSON: sorted keys, two space indent, trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_candidate(
    out_dir: Path,
    results: list[Result],
    manifest: Manifest,
) -> tuple[Path, Path]:
    """Write `results.json` and `manifest.json` for one candidate."""
    results_path = write_json(Path(out_dir) / "results.json", [r.model_dump(mode="json") for r in results])
    manifest_path = write_json(Path(out_dir) / "manifest.json", manifest.model_dump(mode="json"))
    return results_path, manifest_path
