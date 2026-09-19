"""`gate evaluate`. Runs the engine over one suite and prints the outcome. Spec section 4.2."""

from __future__ import annotations

import argparse
from pathlib import Path

from gate.build import GATE_FILES, build_site, dumps


def run(args: argparse.Namespace) -> int:
    """Entry point of `gate evaluate`. Prints verdicts without writing a site."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        report = build_site(
            runs_root=args.runs,
            out=tmp,
            strings_path=args.strings,
            required_path=Path(tmp) / "none.txt",
            bins_path=args.bins,
            gate_files={k: Path(v) for k, v in GATE_FILES.items()},
        )
        data_path = Path(tmp) / "data.json"
        payload = data_path.read_text(encoding="utf-8") if data_path.exists() else "{}"
    import json

    data = json.loads(payload)
    verdicts = []
    for suite in data.get("suites", []):
        for candidate in suite.get("candidates", []):
            if args.candidate and candidate["candidate"] != args.candidate:
                continue
            if args.suite and suite["suite"] != args.suite:
                continue
            verdicts.append(candidate["verdict"])
    print(dumps({"suites": report["suites"], "verdicts": verdicts}), end="")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `gate evaluate` on the CLI root."""
    parser = subparsers.add_parser("evaluate", help="Evaluate gates and print the verdicts.")
    parser.add_argument("--runs", default="runs", help="Runs directory.")
    parser.add_argument("--suite", default="", help="Only this suite.")
    parser.add_argument("--candidate", default="", help="Only this candidate.")
    parser.add_argument("--strings", default="site/strings.json", help="Strings file.")
    parser.add_argument("--bins", default="configs/coverage_bins.yaml", help="Coverage bin config.")
    parser.set_defaults(func=run)


__all__ = ["run", "register"]
