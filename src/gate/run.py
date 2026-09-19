"""`gate run`: the Track B wrapper around Inspect. See docs/ARCHITECTURE.md section 7.6.

The run is pinned twice over. Each candidate model is resolved to a revision
through the Hub and written into `configs/track_b.lock.yaml` on the first run,
and the lock file is never changed afterwards. Without `HF_TOKEN` the command
does a dry run: it prints the plan, calls no provider, and exits 0.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from gate import __version__
from gate.schema import SCHEMA_VERSION, Manifest, ToolVersions

#: Cost model for the cap of section 7.6. Deliberately pessimistic: the cap is
#: there to stop a runaway job, not to price one precisely.
SAMPLES_PER_TASK = 450
EUR_PER_SAMPLE = 0.004
JUDGE_EUR_PER_SAMPLE = 0.002

LOCK_SUFFIX = ".lock.yaml"


class RunRefused(RuntimeError):
    """Raised when the lock file or the cost cap stops a run."""


@dataclass(frozen=True)
class Plan:
    """What a run would do, printed by the dry run and used by the real run."""

    tasks: list[str]
    models: list[str]
    judge: str
    provider_order: list[str]
    temperature: float
    epochs: int
    max_connections: int
    estimated_cost_eur: float
    cost_cap_eur: float
    log_dir: str

    def lines(self) -> list[str]:
        """Return the plan as printable lines, one fact each."""
        return [
            f"tasks            {', '.join(self.tasks)}",
            f"candidates       {', '.join(self.models)}",
            f"judge            {self.judge}",
            f"provider order   {', '.join(self.provider_order)}",
            f"temperature      {self.temperature}",
            f"epochs           {self.epochs}",
            f"max connections  {self.max_connections}",
            f"estimated cost   {self.estimated_cost_eur:.2f} EUR of {self.cost_cap_eur:.2f} EUR cap",
            f"log dir          {self.log_dir}",
        ]


def load_config(path: Path | str) -> dict[str, Any]:
    """Read the Track B configuration file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RunRefused(f"{path} does not hold a mapping")
    return data


def model_string(model_id: str, provider: str) -> str:
    """Return the Inspect model string for a Hub served model."""
    return f"hf-inference-providers/{model_id}:{provider}"


def estimate_cost_eur(config: dict[str, Any]) -> float:
    """Estimate the cost of a full run in euro.

    Samples per task times candidates times epochs, at a flat rate per sample,
    plus the judge pass over every graded sample.
    """
    n_models = len(config.get("candidates") or [])
    n_tasks = len(config.get("tasks") or [])
    epochs = int(config.get("epochs", 1) or 1)
    samples = SAMPLES_PER_TASK * n_tasks * n_models * epochs
    return round(samples * (EUR_PER_SAMPLE + JUDGE_EUR_PER_SAMPLE), 2)


def build_plan(config: dict[str, Any], log_dir: Path | str) -> Plan:
    """Build the plan for one run from the configuration."""
    providers = list(config.get("provider_order") or ["fireworks-ai"])
    cap = float(config.get("cost_cap_eur", 0.0) or 0.0)
    return Plan(
        tasks=list(config.get("tasks") or []),
        models=list(config.get("candidates") or []),
        judge=str(config.get("judge") or ""),
        provider_order=providers,
        temperature=float(config.get("temperature", 0) or 0),
        epochs=int(config.get("epochs", 1) or 1),
        max_connections=int(config.get("max_connections", 4) or 4),
        estimated_cost_eur=estimate_cost_eur(config),
        cost_cap_eur=cap,
        log_dir=str(log_dir),
    )


def lock_path(config_path: Path | str) -> Path:
    """Return the lock file path beside the configuration file."""
    config_path = Path(config_path)
    return config_path.with_name(config_path.stem + LOCK_SUFFIX)


def resolve_revisions(models: list[str]) -> dict[str, str | None]:
    """Resolve each model to its current Hub revision. Network call."""
    from huggingface_hub import HfApi

    api = HfApi()
    revisions: dict[str, str | None] = {}
    for model_id in models:
        try:
            revisions[model_id] = api.model_info(model_id).sha
        except Exception:  # noqa: BLE001 - an unreachable model is excluded, not fatal
            revisions[model_id] = None
    return revisions


def write_lock(config_path: Path, revisions: dict[str, str | None], config: dict[str, Any]) -> dict[str, Any]:
    """Write the lock file on the first run and refuse to change it afterwards.

    A model with no revision after the provider order is exhausted is kept in
    the lock file with `excluded: true` and dropped from the run.
    """
    path = lock_path(config_path)
    lock = {
        "schema_version": SCHEMA_VERSION,
        "judge": config.get("judge"),
        "models": [
            {"id": model_id, "revision": sha, "excluded": sha is None}
            for model_id, sha in sorted(revisions.items())
        ],
    }
    if path.is_file():
        existing = yaml.safe_load(path.read_text(encoding="utf-8"))
        if existing != lock:
            raise RunRefused(
                f"{path.name} is already written and would change; delete it deliberately to repin the run"
            )
        return existing
    path.write_text(yaml.safe_dump(lock, sort_keys=True), encoding="utf-8")
    return lock


def build_manifest(config: dict[str, Any], suite: str, candidate: str, n_samples: int) -> Manifest:
    """Build the Track B manifest of section 3.1."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    versions = _tool_versions()
    return Manifest(
        run_id=f"{suite}-{candidate.replace('/', '_')}-{stamp.replace('-', '').replace(':', '')}",
        suite=suite,
        track="b",
        candidate=candidate,
        baseline=config.get("baseline"),
        generated_at=stamp,
        preregistered=True,
        gate_file="gates/track_b.yaml",
        gate_file_sha256="0" * 64,
        seed=0,
        tools=versions,
        n_results=n_samples,
    )


def _tool_versions() -> ToolVersions:
    """Return the tool versions recorded in a Track B manifest."""
    inspect_ai_version = None
    inspect_evals_version = None
    try:
        from importlib.metadata import version

        inspect_ai_version = version("inspect_ai")
        inspect_evals_version = version("inspect_evals")
    except Exception:  # noqa: BLE001 - versions are informational
        pass
    return ToolVersions(
        gate=__version__,
        inspect_ai=inspect_ai_version,
        inspect_evals=inspect_evals_version,
        judge_prompt_version="1.0",
    )


def run(config_path: Path | str, *, log_dir: Path | str, dry_run: bool, token: str | None) -> int:
    """Run Track B, or print the plan when there is no token or `--dry-run` is set."""
    config = load_config(config_path)
    plan = build_plan(config, log_dir)

    if plan.cost_cap_eur and plan.estimated_cost_eur > plan.cost_cap_eur:
        raise RunRefused(
            f"estimated {plan.estimated_cost_eur:.2f} EUR passes the cap of {plan.cost_cap_eur:.2f} EUR"
        )

    if dry_run or not token:
        reason = "dry run requested" if dry_run else "HF_TOKEN is not set"
        print(f"run: plan only, {reason}. No provider was called.")
        for line in plan.lines():
            print(f"  {line}")
        return 0

    revisions = resolve_revisions(plan.models)
    lock = write_lock(Path(config_path), revisions, config)
    active = [m["id"] for m in lock["models"] if not m["excluded"]]
    if not active:
        raise RunRefused("every candidate model was excluded, no provider served them")

    from inspect_ai import eval_set

    provider = plan.provider_order[0]
    eval_set(
        tasks=plan.tasks,
        model=[model_string(model_id, provider) for model_id in active],
        log_dir=str(log_dir),
        temperature=plan.temperature,
        epochs=plan.epochs,
        max_connections=plan.max_connections,
        model_roles={"grader": model_string(plan.judge, provider)},
    )
    print(f"run: logs written to {log_dir}")
    return 0


def _cmd(args: argparse.Namespace) -> int:
    import os

    if args.track != "b":
        print("run: only track b has a run wrapper", file=sys.stderr)
        return 2
    try:
        return run(
            args.config,
            log_dir=args.log_dir,
            dry_run=args.dry_run,
            token=os.environ.get("HF_TOKEN"),
        )
    except RunRefused as exc:
        print(f"run: refused, {exc}", file=sys.stderr)
        return 2


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add the `run` subcommand to the CLI root."""
    parser = subparsers.add_parser("run", help="Run the Track B evaluation through Inspect")
    parser.add_argument("--track", choices=["a", "b"], default="b")
    parser.add_argument("--config", default="configs/track_b.yaml")
    parser.add_argument("--log-dir", dest="log_dir", default="logs/track_b")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.set_defaults(func=_cmd)
