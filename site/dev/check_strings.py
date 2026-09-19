#!/usr/bin/env python3
"""Check that site/strings.required.txt covers every key the dashboard needs.

Run from anywhere with the repository virtualenv:

    .venv/bin/python site/dev/check_strings.py

Checks, in order:
  1. every literal t("key") in app.js is listed in strings.required.txt
  2. every data-s="key" in index.html is listed in strings.required.txt
  3. every key in strings.required.txt exists in strings.json
  4. every key referenced by the sample data (text_key, note_key, credibility,
     independence, cannot_see) exists in strings.json
  5. every {placeholder} used by app.js for a format string exists in the
     matching strings.json value

Dynamic keys are built at runtime from data, for example "family." plus a
family name. They are covered by check 4 and by the enumerations below.
Rationale keys are merged in by `gate build` and fall back to a placeholder,
so they are never required here.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent

# Prefixes app.js builds at runtime. Every listed suffix must exist.
ENUMERATIONS: dict[str, list[str]] = {
    "status.": ["pass", "fail", "conditional", "not_applicable"],
    "class.": ["hard", "soft", "coverage", "regression", "availability"],
    "tier.": ["nominal", "near_miss", "critical"],
    "bin.": ["empty", "sparse", "ok"],
    "node.": ["goal", "context", "assumption", "strategy", "claim", "evidence", "defeater"],
    "reason.": ["insufficient_n"],
    "waiver.": ["waiver_expired", "waiver_not_permitted"],
    "nav.": ["decision", "gates", "coverage", "case", "evidence", "limits"],
    "family.": ["ped_occluded", "cut_in", "hard_brake", "weather_ramp"],
    "hazard.": ["intersections", "cyclists", "night", "sensor_faults", "multi_actor", "odd_exit"],
}

FORMAT_KEYS = {
    "decision.headline": {"candidate", "verdict", "k", "n", "names"},
    "decision.headline_pass": {"candidate", "n"},
    "decision.waiver_meta": {"signer", "expires"},
    "decision.deviation_meta": {"signer", "changed"},
    "gates.frozen_status": {"status"},
    "gates.worked_example": {"gate", "n", "n_fail", "point", "bound", "threshold"},
    "gates.regression_summary": {"candidate", "baseline", "n", "tier", "ttc"},
    "gates.pairs_all": {"n"},
    "coverage.unbinned": {"n"},
    "coverage.bin_link": {"n", "bin"},
    "coverage.unmapped": {"list"},
    "evidence.count": {"k", "n"},
    "evidence.from_gate": {"gate", "n"},
    "evidence.thumb_alt": {"id"},
    "evidence.count_b": {"k", "n"},
    "gates.fig_rate_alt": {"gate", "point", "bound", "threshold"},
    "gates.fig_count_alt": {"gate", "n_fail", "allowed"},
    "coverage.grid_caption": {"family"},
    "coverage.col.bin": {"i"},
    "coverage.b_bar_alt": {"n"},
}

LITERAL_T = re.compile(r'(?<![A-Za-z0-9_.$])t\(\s*"([^"]+)"\s*[,)]')
DATA_S = re.compile(r'data-s="([^"]+)"')


def collect_data_keys(node, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("text_key", "note_key") and isinstance(value, str):
                out.add(value)
            elif key in ("credibility", "independence", "cannot_see") and isinstance(value, list):
                out.update(v for v in value if isinstance(v, str))
            else:
                collect_data_keys(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_data_keys(item, out)


def main() -> int:
    app = (SITE / "app.js").read_text()
    html = (SITE / "index.html").read_text()
    strings = json.loads((SITE / "strings.json").read_text())
    required_path = SITE / "strings.required.txt"
    required = [
        line.strip() for line in required_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    required_set = set(required)
    problems: list[str] = []

    if len(required) != len(required_set):
        problems.append("strings.required.txt contains a duplicate key")
    if required != sorted(required):
        problems.append("strings.required.txt is not sorted")

    for key in sorted(set(LITERAL_T.findall(app))):
        if key not in required_set:
            problems.append(f"app.js calls t({key!r}) but the key is not in strings.required.txt")

    for key in sorted(set(DATA_S.findall(html))):
        if key not in required_set:
            problems.append(f"index.html marks data-s={key!r} but the key is not in strings.required.txt")

    for prefix, suffixes in ENUMERATIONS.items():
        for suffix in suffixes:
            key = prefix + suffix
            if key not in required_set:
                problems.append(f"enumerated key {key!r} is not in strings.required.txt")

    for key in required:
        if key not in strings:
            problems.append(f"required key {key!r} is missing from strings.json")

    sample_path = SITE / "dev" / "sample_data.json"
    if sample_path.exists():
        data_keys: set[str] = set()
        collect_data_keys(json.loads(sample_path.read_text()), data_keys)
        for key in sorted(data_keys):
            if key not in strings:
                problems.append(f"sample data refers to {key!r} which is missing from strings.json")

    for key, placeholders in FORMAT_KEYS.items():
        value = strings.get(key, "")
        found = set(re.findall(r"\{([a-z_]+)\}", value))
        if found != placeholders:
            problems.append(
                f"format string {key!r} uses {sorted(found)} but app.js supplies {sorted(placeholders)}"
            )

    for problem in problems:
        print("FAIL", problem)
    if problems:
        print(f"{len(problems)} problems")
        return 1
    print(f"ok, {len(required)} required keys, {len(strings)} keys in strings.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
