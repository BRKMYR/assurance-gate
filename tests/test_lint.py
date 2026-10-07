"""Copy linter tests. Section 10 and acceptance tests AC-1, AC-2, AC-20."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "tests" / "fixtures" / "lint_corpus"


def _load_linter():
    spec = importlib.util.spec_from_file_location(
        "lint_copy", REPO_ROOT / "scripts" / "lint_copy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_copy"] = module
    spec.loader.exec_module(module)
    return module


lint_copy = _load_linter()


def violations(paths: list[Path] | None, mode: str) -> list:
    return [f for f in lint_copy.lint(paths, mode, REPO_ROOT) if not f.warning]


def rules(paths: list[Path] | None, mode: str) -> set[str]:
    return {finding.rule for finding in violations(paths, mode)}


# Stand-in terms, so the private list never has to appear in the repository.
FAKE_TERMS = "Acme Mapping\ncs:ZXQ\nre:\\b9Q\\b"


@pytest.fixture
def fake_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STEALTH_TERMS", FAKE_TERMS)


# One failing file per rule, section 10.
FAILING_FILES = {
    "fail_em_dash.md": "em_dash",
    "fail_semicolon.md": "semicolon",
    "fail_exclamation.md": "exclamation",
    "fail_rhetorical_question.md": "rhetorical_question",
    "fail_hyphen_compound.md": "hyphen_compound",
    "fail_sentence_length.md": "sentence_length",
    "fail_banned_word.md": "banned_word",
    "fail_construction.md": "construction",
    "fail_self_certifying.md": "self_certifying",
    "fail_stealth.md": "stealth",
}


@pytest.mark.parametrize("name,rule", sorted(FAILING_FILES.items()))
def test_each_rule_has_a_failing_fixture(name: str, rule: str, fake_terms: None) -> None:
    found = rules([CORPUS / name], "push")
    assert found == {rule}, f"{name} should trip {rule} alone, found {sorted(found)}"


def test_owner_copy_fixture_is_push_clean_and_release_dirty() -> None:
    path = CORPUS / "fail_owner_copy.md"
    assert rules([path], "push") == set()
    assert rules([path], "release") == {"owner_copy"}


def test_pass_fixture_is_clean_in_both_modes() -> None:
    path = CORPUS / "pass.md"
    assert violations([path], "push") == []
    assert violations([path], "release") == []


def test_exit_codes() -> None:
    assert lint_copy.main(["--mode", "push", str(CORPUS / "pass.md")]) == 0
    assert lint_copy.main(["--mode", "push", str(CORPUS / "fail_semicolon.md")]) == 1
    assert lint_copy.main(["--mode", "push", str(REPO_ROOT / "no_such_file.md")]) == 2


def test_finding_output_names_file_line_rule_and_excerpt(capsys: pytest.CaptureFixture) -> None:
    lint_copy.main(["--mode", "push", str(CORPUS / "fail_semicolon.md")])
    captured = capsys.readouterr().out
    assert "fail_semicolon.md:3: semicolon:" in captured
    assert "the gate failed" in captured


def test_stealth_terms_come_from_outside_the_repo(fake_terms: None) -> None:
    patterns = lint_copy.load_stealth_terms()
    assert patterns is not None
    assert [p.pattern for p in patterns] == [r"\bAcme\ Mapping\b", r"\bZXQ\b", r"\b9Q\b"]


def test_stealth_catches_the_case_sensitive_and_regex_terms(tmp_path: Path, fake_terms: None) -> None:
    sample = tmp_path / "leak.md"
    sample.write_text(
        "The fleet reached 9Q vehicles.\n"
        "Written at /Users/someone/notes.\n"
        "Write to someone@example.com.\n"
        "Sold by ZXQ.\n"
        "Sold by zxq.\n",
        encoding="utf-8",
    )
    found = [f for f in lint_copy.lint([sample], "push", tmp_path) if f.rule == "stealth"]
    assert len(found) == 4


def test_missing_terms_fail_in_ci_and_warn_locally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STEALTH_TERMS", raising=False)
    monkeypatch.setenv("STEALTH_TERMS_FILE", str(tmp_path / "absent.txt"))
    monkeypatch.setenv("CI", "true")
    assert "stealth_terms_missing" in rules([CORPUS / "pass.md"], "push")
    monkeypatch.delenv("CI")
    assert violations([CORPUS / "pass.md"], "push") == []


def test_docs_are_never_linted() -> None:
    """The stealth terms may appear in docs/, which is outside every lint path."""
    assert not any(glob.startswith("docs/") for glob in lint_copy.DEFAULT_PROSE_GLOBS)
    assert "docs" not in lint_copy.STEALTH_ROOTS


# --- Acceptance tests ------------------------------------------------------


def test_ac_1_lint_push_passes_on_the_repo() -> None:
    found = violations(None, "push")
    assert found == [], "\n".join(finding.render() for finding in found)


def test_ac_2_lint_release_fails_while_a_placeholder_remains() -> None:
    found = violations([CORPUS / "fail_owner_copy.md"], "release")
    assert any(finding.rule == "owner_copy" for finding in found)
    assert not any(finding.rule == "owner_copy" for finding in violations([CORPUS / "fail_owner_copy.md"], "push"))


def test_ac_2_lint_release_passes_on_the_corpus_pass_file() -> None:
    assert lint_copy.main(["--mode", "release", str(CORPUS / "pass.md")]) == 0


def test_ac_20_external_holds_the_patch_and_the_profile_readme() -> None:
    patch = REPO_ROOT / "external" / "brkmyr.com" / "gate.patch"
    profile = REPO_ROOT / "external" / "profile-readme" / "README.md"
    assert patch.is_file()
    assert profile.is_file()
    found = violations([patch, profile], "push")
    assert found == [], "\n".join(finding.render() for finding in found)
