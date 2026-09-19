"""`gate build` tests. Spec sections 3.11, 3.12 and 8. Acceptance tests AC-16 and AC-17."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gate.build import (
    BUILT_IN_STRINGS,
    BuildError,
    build_site,
    check_required_strings,
    discover_suites,
    dumps,
    load_strings,
)
from gate.schema import SCHEMA_VERSION

from helpers_a import FIXTURES, REPO, RUNS_FIXTURE

GATE_FILES = {"a": REPO / "gates/track_a.yaml", "b": REPO / "gates/track_b.yaml"}


def run_build(out: Path, runs_root: Path = RUNS_FIXTURE, **overrides) -> dict:
    """Build from the fixture runs into `out`."""
    kwargs = {
        "runs_root": runs_root,
        "out": out,
        "strings_path": None,
        "required_path": out / "missing.txt",
        "bins_path": REPO / "configs/coverage_bins.yaml",
        "gate_files": dict(GATE_FILES),
    }
    kwargs.update(overrides)
    return build_site(**kwargs)


def test_discover_suites_finds_the_fixture_suite() -> None:
    suites = discover_suites(RUNS_FIXTURE)
    assert [s.name for s in suites] == ["fixture"]


def test_ac_16_build_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    run_build(first)
    run_build(second)
    assert (first / "data.json").read_bytes() == (second / "data.json").read_bytes()


def test_ac_16_build_matches_the_golden_data_file(tmp_path: Path) -> None:
    run_build(tmp_path / "out")
    assert (tmp_path / "out" / "data.json").read_bytes() == (FIXTURES / "data.json").read_bytes()


def test_ac_17_required_strings_keys_all_exist() -> None:
    repo = REPO
    required = repo / "site/strings.required.txt"
    strings = load_strings(repo / "site/strings.json" if (repo / "site/strings.json").exists() else None)
    for track in ("a", "b"):
        from gate.gates import load_gate_file, rationale_strings

        strings.update(rationale_strings(load_gate_file(GATE_FILES[track])))
    missing = check_required_strings(strings, required)
    assert missing == [], f"missing strings keys: {missing}"


def test_ac_17_the_checker_reports_a_missing_key(tmp_path: Path) -> None:
    required = tmp_path / "strings.required.txt"
    required.write_text("decision.headline\n# a comment\nnot.a.key\n", encoding="utf-8")
    assert check_required_strings(BUILT_IN_STRINGS, required) == ["not.a.key"]
    with pytest.raises(BuildError):
        run_build(tmp_path / "out", required_path=required)


def test_build_writes_data_thumbnails_and_strings(tmp_path: Path) -> None:
    out = tmp_path / "out"
    report = run_build(out)
    assert report["written"] == ["data.json"]
    assert report["thumbnails"] == 2
    assert (out / "thumbs" / "ped_occluded_cautious_idm_core-ped-0001.png").exists()
    strings = json.loads((out / "strings.json").read_text())
    assert strings["rationale.a.hard.ped_collision"].startswith("[[OWNER_COPY")


def test_data_file_envelope_and_suite_block(tmp_path: Path) -> None:
    out = tmp_path / "out"
    run_build(out)
    data = json.loads((out / "data.json").read_text())
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["built_with"].startswith("gate ")
    assert data["track"] == "a"
    suite = data["suites"][0]
    assert suite["suite"] == "fixture"
    assert suite["preregistered"] is False
    assert len(suite["gate_file_sha256"]) == 64
    assert suite["credibility"] and suite["independence"]
    names = [c["candidate"] for c in suite["candidates"]]
    assert names == sorted(names)


def test_candidate_block_carries_every_section(tmp_path: Path) -> None:
    out = tmp_path / "out"
    run_build(out)
    data = json.loads((out / "data.json").read_text())
    candidate = data["suites"][0]["candidates"][0]
    assert candidate["candidate"] == "cautious_idm"
    assert candidate["verdict"]["verdict"] in {"GO", "NO_GO", "CONDITIONAL"}
    assert len(candidate["gates"]) == 9
    assert candidate["coverage"]["rows"]
    assert candidate["regression"]["n_pairs"] == 1
    assert candidate["case"]["root"] == "g0"
    assert candidate["residual_risk"]
    assert candidate["worked_example"]["note_key"] == "gates.worked_example"
    assert candidate["results"]


def test_no_private_field_reaches_the_output(tmp_path: Path) -> None:
    out = tmp_path / "out"
    run_build(out)
    assert "trajectory_log" not in (out / "data.json").read_text()


def test_floats_are_rounded_to_four_decimals() -> None:
    assert dumps({"x": 0.123456789}) == '{\n  "x": 0.1235\n}\n'


def test_schema_version_mismatch_fails_the_build(tmp_path: Path) -> None:
    import shutil

    runs = tmp_path / "runs"
    shutil.copytree(RUNS_FIXTURE, runs)
    manifest_path = runs / "fixture" / "idm" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = "9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BuildError):
        run_build(tmp_path / "out", runs_root=runs)


def test_missing_runs_fall_back_to_the_fixtures(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(REPO)
    report = run_build(tmp_path / "out", runs_root=tmp_path / "empty")
    assert report["suites"] == ["fixture"]


def test_strings_fall_back_to_the_internal_default(tmp_path: Path) -> None:
    assert load_strings(tmp_path / "nothing.json") == BUILT_IN_STRINGS
    assert "decision.headline" in BUILT_IN_STRINGS
