"""Command line root. Subcommands register themselves from their modules.

Owned by workstream A. Other workstreams add a `register(subparsers)` function
in their own module and never edit this file.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from gate import __version__

SUBCOMMAND_MODULES = (
    "gate.engine_cli",   # evaluate (A)
    "gate.build",        # build (A)
    "gate.preregister",  # preregister (B)
    "gate.ingest",       # ingest (B)
    "gate.run",          # run (B)
    "gate.publish",      # publish (D)
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gate", description="Evaluation results in, release decision out.")
    parser.add_argument("--version", action="version", version=f"gate {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    for name in SUBCOMMAND_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        register = getattr(module, "register", None)
        if register is not None:
            register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
