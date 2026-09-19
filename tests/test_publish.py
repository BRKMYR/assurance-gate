"""`gate publish` tests. Section 8. The Hugging Face API is mocked, no network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from gate import publish


class FakeApi:
    """Records every call instead of talking to the hub."""

    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, token: str | None = None) -> None:
        self.token = token
        FakeApi.calls.append(("__init__", {"token": token}))

    def upload_folder(self, **kwargs: Any) -> str:
        FakeApi.calls.append(("upload_folder", kwargs))
        return "commit"

    def upload_file(self, **kwargs: Any) -> str:
        FakeApi.calls.append(("upload_file", kwargs))
        return "commit"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("MIRROR_TOKEN", raising=False)
    monkeypatch.delenv("MIRROR_CHECKOUT", raising=False)
    FakeApi.calls = []


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (tmp_path / "site" / "data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "space").mkdir()
    (tmp_path / "space" / "README.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    (tmp_path / "dataset").mkdir()
    (tmp_path / "dataset" / "README.md").write_text("# card\n", encoding="utf-8")
    run_dir = tmp_path / "runs" / "demo" / "idm"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text("[]", encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({"suite": "demo"}), encoding="utf-8")
    (run_dir / "notes.txt").write_text("private", encoding="utf-8")
    prereg = tmp_path / "preregistration"
    prereg.mkdir()
    (prereg / "a-holdout.json").write_text("{}", encoding="utf-8")
    return tmp_path


def args_for(root: Path, dry_run: bool = False, tag: str = "v1.0") -> argparse.Namespace:
    return argparse.Namespace(tag=tag, dry_run=dry_run, root=root, func=publish.run)


def snapshot(root: Path) -> dict[str, float]:
    return {
        str(path.relative_to(root)): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_register_adds_the_publish_subcommand() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    publish.register(subparsers)
    parsed = parser.parse_args(["publish", "--tag", "v1.0", "--dry-run"])
    assert parsed.tag == "v1.0"
    assert parsed.dry_run is True
    assert parsed.func is publish.run


def test_tag_is_required() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    publish.register(subparsers)
    with pytest.raises(SystemExit):
        parser.parse_args(["publish"])


def test_dry_run_prints_every_operation_and_touches_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(publish, "HfApi", FakeApi)
    before = snapshot(repo)
    assert publish.run(args_for(repo, dry_run=True)) == 0
    assert snapshot(repo) == before
    assert FakeApi.calls == []
    out = capsys.readouterr().out
    assert "N20X/assurance-gate" in out
    assert "N20X/assurance-gate-runs" in out
    assert "delete_patterns=['*']" in out
    assert "space/README.md" in out
    assert "dataset/README.md" in out
    assert "runs/demo/idm/results.json" in out
    assert "runs/demo/idm/manifest.json" in out
    assert "preregistration/a-holdout.json" in out
    assert "mirror skipped" in out


def test_without_hf_token_a_real_run_exits_2(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(publish, "HfApi", FakeApi)
    assert publish.run(args_for(repo)) == publish.EXIT_NO_TOKEN
    assert FakeApi.calls == []
    assert "HF_TOKEN is not set" in capsys.readouterr().out


def test_space_upload_uses_delete_patterns_and_restores_the_card(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setattr(publish, "HfApi", FakeApi)
    assert publish.run(args_for(repo)) == 0

    folder = next(
        kwargs
        for name, kwargs in FakeApi.calls
        if name == "upload_folder" and kwargs["repo_id"] == publish.SPACE_REPO_ID
    )
    assert folder["folder_path"] == str(repo / "site")
    assert folder["repo_type"] == "space"
    assert folder["delete_patterns"] == ["*"]

    card = next(
        kwargs
        for name, kwargs in FakeApi.calls
        if name == "upload_file" and kwargs["repo_id"] == publish.SPACE_REPO_ID
    )
    assert card["path_or_fileobj"] == str(repo / "space" / "README.md")
    assert card["path_in_repo"] == "README.md"
    # The card is restored after the folder upload cleared the Space.
    order = [name for name, kwargs in FakeApi.calls if kwargs.get("repo_id") == publish.SPACE_REPO_ID]
    assert order == ["upload_folder", "upload_file"]


def test_dataset_upload_carries_results_manifests_preregistration_and_card(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setattr(publish, "HfApi", FakeApi)
    assert publish.run(args_for(repo)) == 0

    folder = next(
        kwargs
        for name, kwargs in FakeApi.calls
        if name == "upload_folder" and kwargs["repo_id"] == publish.DATASET_REPO_ID
    )
    assert folder["repo_type"] == "dataset"
    assert folder["allow_patterns"] == [
        "runs/**/results.json",
        "runs/**/manifest.json",
        "preregistration/*.json",
    ]
    card = next(
        kwargs
        for name, kwargs in FakeApi.calls
        if name == "upload_file" and kwargs["repo_id"] == publish.DATASET_REPO_ID
    )
    assert card["path_in_repo"] == "README.md"


def test_dataset_file_selection_skips_private_files(repo: Path) -> None:
    names = [str(path.relative_to(repo)) for path in publish.dataset_files(repo)]
    assert names == [
        "preregistration/a-holdout.json",
        "runs/demo/idm/manifest.json",
        "runs/demo/idm/results.json",
    ]
    assert not any(name.endswith("notes.txt") for name in names)


def test_commit_message_format() -> None:
    assert publish.commit_message("v1.0", "2026-09-21T10:15:00Z") == (
        "gate publish v1.0 2026-09-21T10:15:00Z"
    )
    assert publish.utc_now().endswith("Z")


def test_mirror_runs_only_with_a_mirror_token(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setattr(publish, "HfApi", FakeApi)
    called: list[str] = []
    monkeypatch.setattr(publish, "mirror_site", lambda *a, **k: called.append("mirror"))
    assert publish.run(args_for(repo)) == 0
    assert called == []
    assert "MIRROR_TOKEN is not set" in capsys.readouterr().out

    monkeypatch.setenv("MIRROR_TOKEN", "mirror-secret")
    assert publish.run(args_for(repo)) == 0
    assert called == ["mirror"]


def test_mirror_copies_the_site_under_gate_live(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "website"
    (checkout / ".git").mkdir(parents=True)
    monkeypatch.setenv("MIRROR_CHECKOUT", str(checkout))
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(publish, "_git", lambda c, *a: _fake_git(commands, c, *a))
    publish.mirror_site(repo, "gate publish v1.0 2026-09-21T10:15:00Z", "token")
    assert (checkout / "gate" / "live" / "index.html").is_file()
    assert any("commit" in args for args in commands)
    assert any("push" in args for args in commands)


def _fake_git(commands: list[tuple[str, ...]], checkout: Path, *args: str):
    commands.append(args)

    class Result:
        stdout = "?? gate/live/index.html\n"

    return Result()


def test_mirror_without_a_checkout_is_skipped(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MIRROR_CHECKOUT", str(tmp_path / "missing"))
    publish.mirror_site(repo, "message", "token")
    assert "mirror checkout missing" in capsys.readouterr().out
