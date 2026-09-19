"""Sanitiser tests, AC-13. Every string in the leak corpus must come out clean."""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path

from gate import sanitise

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "tests/fixtures/leak_corpus.json"

HOST = socket.gethostname()
HOSTS = sanitise.hostnames()


def _corpus() -> dict:
    """Read the corpus and substitute the real host name for the placeholder."""
    raw = CORPUS.read_text(encoding="utf-8").replace("{host}", HOST)
    return json.loads(raw)


def test_the_corpus_holds_ten_strings() -> None:
    assert len(_corpus()["strings"]) == 10


def test_ac13_every_corpus_string_is_cleaned() -> None:
    for text in _corpus()["strings"]:
        cleaned = sanitise.sanitise_text(text)
        assert not sanitise.PATH_RE.search(cleaned), text
        assert not sanitise.EMAIL_RE.search(cleaned), text
        for host in HOSTS:
            assert not re.search(re.escape(host), cleaned, flags=re.IGNORECASE), text


def test_ac13_placeholders_replace_what_was_removed() -> None:
    cleaned = sanitise.sanitise_text("/Users/someone/runs/demo/results.json")
    assert cleaned == sanitise.PATH_PLACEHOLDER
    assert sanitise.sanitise_text("mail someone@example.com now") == (
        f"mail {sanitise.EMAIL_PLACEHOLDER} now"
    )
    assert sanitise.HOST_PLACEHOLDER in sanitise.sanitise_text(f"built on {HOST}")


def test_ac13_environment_keys_are_dropped_from_a_log_object() -> None:
    cleaned = sanitise.sanitise_obj(_corpus()["object"])
    eval_block = cleaned["eval"]
    assert eval_block["task"] == "xstest"
    for key in sanitise.DROPPED_KEYS:
        assert key not in eval_block
        assert key not in eval_block["metadata"]
    assert eval_block["metadata"]["keep"] == sanitise.PATH_PLACEHOLDER


def test_a_json_file_is_cleaned_in_place(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text(
        json.dumps({"cwd": "/Users/someone", "note": "see /home/x/a.json"}), encoding="utf-8"
    )
    assert sanitise.sanitise_json_file(path) is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"note": f"see {sanitise.PATH_PLACEHOLDER}"}
    assert sanitise.sanitise_json_file(path) is False


def test_a_clean_tree_reports_no_change(tmp_path: Path) -> None:
    path = tmp_path / "clean.json"
    path.write_text(json.dumps({"a": 1}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    assert sanitise.sanitise_tree(tmp_path) == []
