"""`gate ingest` and `gate run` tests, AC-15. No network in this file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml

from gate import ingest, run

REPO = Path(__file__).resolve().parents[1]

SCENARIO = {
    "scenario_id": "t-ped-0001",
    "family": "ped_occluded",
    "description": "Pedestrian occluded by a parked vehicle.",
    "ego": {"initial": {"x_m": 0.0, "speed_mps": 11.6311}},
    "actors": [
        {"actor_id": "occluder", "kind": "static", "initial": {"x_m": 63.7636}, "phases": []},
        {
            "actor_id": "pedestrian",
            "kind": "pedestrian",
            "initial": {"x_m": 63.7636},
            "phases": [
                {"lateral_speed_mps": 0.0, "trigger": {"type": "time", "at_time_s": 0.0}},
                {"lateral_speed_mps": 1.0936, "trigger": {"type": "ego_x", "ego_x_m": 34.1672}},
            ],
        },
    ],
}

RESULT = {
    "schema_version": "1.0",
    "scenario_id": "t-ped-0001",
    "suite": "core",
    "family": "ped_occluded",
    "planner": "cautious_idm",
    "n_steps": 151,
    "duration_s": 15.0,
    "trajectory_log": "/Users/someone/core/cautious_idm/t-ped-0001.jsonl",
    "metrics": {"d_min_m": 1.5, "collision": False, "severity_index": 0},
    "score": 91.0,
    "severity_tier": "nominal",
}


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """An AVSB style run directory with one scenario and one planner."""
    root = tmp_path / "artifacts/core"
    (root / "ped_occluded").mkdir(parents=True)
    (root / "ped_occluded/t-ped-0001.yaml").write_text(yaml.safe_dump(SCENARIO), encoding="utf-8")
    (root / "cautious_idm").mkdir(parents=True)
    (root / "cautious_idm/t-ped-0001.result.json").write_text(json.dumps(RESULT), encoding="utf-8")
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An assurance-gate repository root with a gate file."""
    root = tmp_path / "repo"
    (root / "gates").mkdir(parents=True)
    (root / "gates/track_a.yaml").write_text("frozen: true\n", encoding="utf-8")
    return root


def _preregistration(repo: Path, suite: str, released_at: str) -> None:
    path = repo / "runs" / suite / "preregistration.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"github_release": released_at, "gate_file_sha256": "0" * 64}), encoding="utf-8"
    )


def test_a_run_after_the_published_hash_is_ingested(repo: Path, source: Path) -> None:
    _preregistration(repo, "holdout", "2026-09-21T09:58:11Z")
    out = ingest.ingest(
        repo,
        track="a",
        suite="holdout",
        source=source,
        scenarios=source,
        plots=None,
        candidate="cautious_idm",
        baseline="idm",
        generated_at="2026-09-21T10:15:00Z",
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["preregistered"] is True
    assert manifest["run_id"] == "holdout-cautious_idm-20260921T101500Z"
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results[0]["description"].startswith("Pedestrian occluded")
    assert results[0]["parameters"]["trigger_offset_m"] == 29.5964


def test_ac15_refuses_a_manifest_older_than_the_published_hash(repo: Path, source: Path) -> None:
    _preregistration(repo, "holdout", "2026-09-21T09:58:11Z")
    with pytest.raises(ingest.IngestRefused, match="precedes the published gate hash"):
        ingest.ingest(
            repo,
            track="a",
            suite="holdout",
            source=source,
            scenarios=source,
            plots=None,
            candidate="cautious_idm",
            baseline="idm",
            generated_at="2026-09-20T08:00:00Z",
        )


def test_ac15_accepts_suite_demo_despite_an_older_timestamp(repo: Path, source: Path) -> None:
    _preregistration(repo, "demo", "2026-09-21T09:58:11Z")
    out = ingest.ingest(
        repo,
        track="a",
        suite="demo",
        source=source,
        scenarios=source,
        plots=None,
        candidate="cautious_idm",
        baseline="idm",
        generated_at="2026-08-23T10:03:47Z",
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["preregistered"] is False
    assert manifest["suite"] == "demo"


def test_without_a_preregistration_the_suite_is_not_preregistered(repo: Path, source: Path) -> None:
    out = ingest.ingest(
        repo,
        track="a",
        suite="holdout",
        source=source,
        scenarios=source,
        plots=None,
        candidate="cautious_idm",
        baseline=None,
        generated_at="2026-09-21T10:15:00Z",
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["preregistered"] is False
    assert manifest["baseline"] is None


def test_an_unknown_candidate_is_refused(repo: Path, source: Path) -> None:
    with pytest.raises(ingest.IngestRefused, match="no results for candidate"):
        ingest.ingest(
            repo,
            track="a",
            suite="holdout",
            source=source,
            scenarios=source,
            plots=None,
            candidate="nobody",
            baseline=None,
        )


def test_the_committed_demo_suite_holds_three_candidates() -> None:
    demo = REPO / "runs/demo"
    if not demo.is_dir():
        pytest.skip("runs/demo is not ingested in this checkout")
    candidates = sorted(p.name for p in demo.iterdir() if p.is_dir() and p.name != "thumbs")
    assert candidates == ["cautious_idm", "constant_velocity", "idm"]
    for name in candidates:
        manifest = json.loads((demo / name / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["preregistered"] is False
        assert manifest["suite"] == "demo"
        assert len(json.loads((demo / name / "results.json").read_text(encoding="utf-8"))) == 60
    assert json.loads((demo / "idm/manifest.json").read_text(encoding="utf-8"))["baseline"] is None


# --- gate run ---------------------------------------------------------------


def test_the_track_b_config_matches_the_spec_defaults() -> None:
    config = run.load_config(REPO / "configs/track_b.yaml")
    assert config["tasks"] == ["xstest", "strong_reject"]
    assert config["baseline"] == "Qwen/Qwen2.5-7B-Instruct"
    assert config["judge"] == "openai/gpt-oss-120b"
    assert config["provider_order"] == ["fireworks-ai", "together", "nscale", "novita"]
    assert config["cost_cap_eur"] == 25
    assert [h["id"] for h in config["hazards"]][0] == "violent_crimes"


def test_a_dry_run_prints_the_plan_and_calls_nobody(tmp_path: Path, capsys) -> None:
    code = run.run(REPO / "configs/track_b.yaml", log_dir=tmp_path, dry_run=True, token=None)
    out = capsys.readouterr().out
    assert code == 0
    assert "No provider was called." in out
    assert "hf-inference-providers" not in out
    assert "estimated cost" in out


def test_without_a_token_the_run_falls_back_to_the_plan(tmp_path: Path, capsys) -> None:
    code = run.run(REPO / "configs/track_b.yaml", log_dir=tmp_path, dry_run=False, token=None)
    assert code == 0
    assert "HF_TOKEN is not set" in capsys.readouterr().out


def test_the_cost_cap_stops_a_run(tmp_path: Path) -> None:
    config = tmp_path / "small.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "tasks": ["xstest", "strong_reject"],
                "candidates": ["a/b", "c/d", "e/f"],
                "judge": "j/k",
                "epochs": 1,
                "cost_cap_eur": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(run.RunRefused, match="passes the cap"):
        run.run(config, log_dir=tmp_path, dry_run=True, token=None)


def test_the_lock_file_is_written_once_and_never_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "track_b.yaml"
    config_path.write_text(yaml.safe_dump({"judge": "j/k"}), encoding="utf-8")
    config = run.load_config(config_path)
    run.write_lock(config_path, {"a/b": "sha1"}, config)
    lock = yaml.safe_load(run.lock_path(config_path).read_text(encoding="utf-8"))
    assert lock["models"] == [{"id": "a/b", "revision": "sha1", "excluded": False}]
    run.write_lock(config_path, {"a/b": "sha1"}, config)
    with pytest.raises(run.RunRefused, match="would change"):
        run.write_lock(config_path, {"a/b": "sha2"}, config)


def test_a_model_with_no_revision_is_excluded(tmp_path: Path) -> None:
    config_path = tmp_path / "track_b.yaml"
    config_path.write_text(yaml.safe_dump({"judge": "j/k"}), encoding="utf-8")
    lock = run.write_lock(config_path, {"a/b": None}, run.load_config(config_path))
    assert lock["models"][0]["excluded"] is True


def test_the_model_string_carries_the_provider() -> None:
    assert run.model_string("Qwen/Qwen2.5-7B-Instruct", "fireworks-ai") == (
        "hf-inference-providers/Qwen/Qwen2.5-7B-Instruct:fireworks-ai"
    )


def test_the_run_subcommand_only_serves_track_b(capsys) -> None:
    assert run._cmd(argparse.Namespace(track="a", config="x", log_dir="y", dry_run=True)) == 2
    assert "only track b" in capsys.readouterr().err
