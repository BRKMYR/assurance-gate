"""`gate preregister` tests, AC-14. `gh` is mocked, no network in this file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gate import preregister

GATE_FILE = """schema_version: "1.0"
track: a
suite: holdout
frozen: true
gates:
  - id: a.hard.ped_collision
    class: hard
    kind: count
    family: ped_occluded
    predicate: "metrics.collision == false"
    threshold: 0
    direction: max
    severity: high
    min_n: 14
    rationale: "A pedestrian collision blocks a release."
    source: "UL 4600:2023 Section 8 (informative)"
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository root with a ready gate file and an empty suite directory."""
    (tmp_path / "gates").mkdir()
    (tmp_path / "gates/track_a.yaml").write_text(GATE_FILE, encoding="utf-8")
    (tmp_path / "runs/holdout").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Mock `gh` and drop `HF_TOKEN`. Returns the recorded release calls."""
    calls: list[tuple[str, str, str]] = []

    def fake_release(tag: str, title: str, body: str) -> str:
        calls.append((tag, title, body))
        return "2026-09-21T09:58:11Z"

    monkeypatch.setattr(preregister, "gh_release_create", fake_release)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    return calls


def test_a_ready_suite_is_preregistered(repo: Path, no_network: list, capsys) -> None:
    record = preregister.preregister(repo, "a", "holdout")
    digest = record["gate_file_sha256"]
    assert record["tag"] == f"gates-a-holdout-{digest[:8]}"
    assert record["github_release"] == "2026-09-21T09:58:11Z"
    assert record["hf_dataset_commit"] is None
    assert "HF_TOKEN is not set" in capsys.readouterr().err
    written = json.loads((repo / "runs/holdout/preregistration.json").read_text(encoding="utf-8"))
    assert written == record
    assert no_network[0][2].splitlines()[1] == f"sha256 {digest}"


def test_ac14_refuses_with_a_manifest_present(repo: Path, no_network: list) -> None:
    (repo / "runs/holdout/cautious_idm").mkdir(parents=True)
    (repo / "runs/holdout/cautious_idm/manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(preregister.PreregisterRefused, match="manifest"):
        preregister.preregister(repo, "a", "holdout")
    assert no_network == []


def test_ac14_refuses_with_an_owner_copy_placeholder(repo: Path, no_network: list) -> None:
    gate_file = repo / "gates/track_a.yaml"
    gate_file.write_text(
        GATE_FILE.replace(
            '"A pedestrian collision blocks a release."',
            '"[[OWNER_COPY: rationale a.hard.ped_collision]]"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(preregister.PreregisterRefused, match="placeholder"):
        preregister.preregister(repo, "a", "holdout")
    assert no_network == []


def test_ac14_refuses_without_frozen_true(repo: Path, no_network: list) -> None:
    gate_file = repo / "gates/track_a.yaml"
    gate_file.write_text(GATE_FILE.replace("frozen: true", "frozen: false"), encoding="utf-8")
    with pytest.raises(preregister.PreregisterRefused, match="frozen"):
        preregister.preregister(repo, "a", "holdout")
    assert no_network == []


def test_the_hash_covers_the_whole_file(repo: Path) -> None:
    gate_file = repo / "gates/track_a.yaml"
    before = preregister.sha256_of(gate_file)
    gate_file.write_text(GATE_FILE + "# a trailing comment\n", encoding="utf-8")
    assert preregister.sha256_of(gate_file) != before


def test_the_command_returns_two_on_a_refusal(repo: Path, no_network: list, capsys) -> None:
    import argparse

    (repo / "runs/holdout/manifest.json").write_text("{}", encoding="utf-8")
    args = argparse.Namespace(root=str(repo), track="a", suite="holdout")
    assert preregister._cmd(args) == 2
    assert "refused" in capsys.readouterr().err


def test_the_subcommand_registers_with_a_func(capsys) -> None:
    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    preregister.register(subparsers)
    args = parser.parse_args(["preregister", "--suite", "holdout"])
    assert args.func is preregister._cmd
