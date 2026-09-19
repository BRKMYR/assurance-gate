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


def _resolve_token() -> str | None:
    """HF_TOKEN from the environment, else the token stored by `hf auth login`."""
    import os
    from huggingface_hub import get_token

    return os.environ.get("HF_TOKEN") or get_token()


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


def pick_provider(model_id: str, provider_order: list[str]) -> str | None:
    """First provider that answers a one token request for the model.

    Providers are tried in the configured order first, then every other
    provider the Hub lists for the model. The Hub mapping alone is not enough,
    some listed providers only serve a model on a dedicated endpoint. Returns
    None when no provider answers, which leaves routing to the Hub.
    """
    from huggingface_hub import HfApi, InferenceClient

    try:
        info = HfApi().model_info(model_id, expand=["inferenceProviderMapping"])
        mapping = getattr(info, "inference_provider_mapping", None) or []
        served = [x for x in (getattr(m, "provider", None) for m in mapping) if x]
    except Exception:  # network or Hub error, let routing decide
        return None
    ordered = [p for p in provider_order if p in served] + [p for p in served if p not in provider_order]
    for provider in ordered:
        try:
            InferenceClient(provider=provider).chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=3,
                temperature=0,
            )
            return provider
        except Exception:
            continue
    return None


def build_tasks(names: list[str], judge: str, max_tokens: int | None = None) -> list:
    """Instantiate the configured tasks with the judge passed as a task argument.

    `xstest` grades with `scorer_model` and runs one subset per task, so it is
    expanded into a safe run and an unsafe run. `strong_reject` grades with
    `judge_llm`. Any other name is passed through as an Inspect task path.
    """
    tasks: list = []
    for name in names:
        if name == "xstest":
            from inspect_evals.xstest import xstest

            tasks.append(xstest(subset="safe", scorer_model=judge))
            tasks.append(xstest(subset="unsafe", scorer_model=judge))
        elif name == "strong_reject":
            from inspect_evals.strong_reject import strong_reject

            tasks.append(strong_reject(judge_llm=judge))
        else:
            tasks.append(name if "/" in name else f"inspect_evals/{name}")
    if max_tokens:
        for task in tasks:
            config = getattr(task, "config", None)
            if config is not None:
                config.max_tokens = max_tokens
    return tasks


def model_string(model_id: str, provider: str | None) -> str:
    """Return the Inspect model string for a Hub served model."""
    if provider is None:
        return f"hf-inference-providers/{model_id}"
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


def write_outputs(
    root: Path, suite: str, log_dir: Path, config: dict[str, Any], active: list[str], *, notes: str = ""
) -> list[Path]:
    """Write `samples.json` and a manifest per candidate from the logs of one run.

    The manifest carries the gate file hash, the pre registration timestamps
    when `runs/<suite>/preregistration.json` exists, and the earliest log start
    as `generated_at`. A run whose earliest start precedes the published hash is
    written with `preregistered: false`, never refused, so the dashboard shows it
    with the demo ribbon instead of hiding it.
    """
    import json as _json
    from collections import defaultdict

    from inspect_ai.log import read_eval_log

    from gate.adapters.inspect_ import read_samples
    from gate.gates import sha256_file
    from gate.schema import PublishedAt

    record = None
    record_path = root / "runs" / suite / "preregistration.json"
    if record_path.is_file():
        record = _json.loads(record_path.read_text(encoding="utf-8"))

    by_model: dict[str, list] = defaultdict(list)
    started: dict[str, str] = {}
    for logfile in sorted(Path(log_dir).glob("*.eval")):
        header = read_eval_log(str(logfile), header_only=True)
        if header.status != "success":
            continue
        model = header.eval.model
        created = str(header.eval.created)
        started[model] = min(started.get(model, created), created)
        by_model[model].extend(read_samples(logfile))

    written: list[Path] = []
    gate_hash = sha256_file(root / "gates" / "track_b.yaml")
    for model, samples in sorted(by_model.items()):
        candidate = next((m for m in active if m in model), model)
        out_dir = root / "runs" / suite / candidate.replace("/", "_")
        out_dir.mkdir(parents=True, exist_ok=True)
        samples = sorted(samples, key=lambda x: (x.task, x.sample_id))
        manifest = build_manifest(config, suite, candidate, len(samples))
        stamp = started[model].replace("+00:00", "Z")
        if "T" in stamp and not stamp.endswith("Z"):
            stamp = stamp.split(".")[0] + "Z"
        manifest.generated_at = stamp
        manifest.gate_file_sha256 = gate_hash
        manifest.notes = notes
        if record:
            manifest.gate_published_at = PublishedAt(
                github_release=record.get("github_release"),
                hf_dataset_commit=record.get("hf_dataset_commit"),
            )
            manifest.preregistered = bool(record.get("github_release")) and stamp > record["github_release"]
        else:
            manifest.preregistered = False
        (out_dir / "samples.json").write_text(
            _json.dumps([x.model_dump() for x in samples], indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (out_dir / "manifest.json").write_text(
            _json.dumps(manifest.model_dump(), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
        written += [out_dir / "samples.json", out_dir / "manifest.json"]
    return written


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


def run(
    config_path: Path | str,
    *,
    log_dir: Path | str,
    dry_run: bool,
    token: str | None,
    suite: str = "trackb",
    notes: str = "",
) -> int:
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

    chosen = {m: pick_provider(m, plan.provider_order) for m in active}
    judge_provider = pick_provider(plan.judge, plan.provider_order)
    for m, prov in chosen.items():
        print(f"run: {m} via {prov or 'auto routing'}")
    print(f"run: judge {plan.judge} via {judge_provider or 'auto routing'}")
    judge = model_string(plan.judge, judge_provider)
    gen = config.get("reasoning") or {}
    max_tokens = int(gen.get("max_tokens") or 2048)
    print(f"run: max_tokens {max_tokens}, reasoning effort {gen.get('effort', 'default')}")
    eval_set(
        tasks=build_tasks(plan.tasks, judge, max_tokens),
        model=[model_string(model_id, chosen[model_id]) for model_id in active],
        log_dir=str(log_dir),
        temperature=plan.temperature,
        epochs=plan.epochs,
        max_connections=plan.max_connections,
        max_tokens=max_tokens,
        reasoning_effort=gen.get("effort"),
    )
    print(f"run: logs written to {log_dir}")
    written = write_outputs(Path("."), suite, Path(log_dir), config, active, notes=notes)
    for path in written:
        print(f"run: wrote {path}")
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
            suite=args.suite,
            notes=args.notes,
            token=_resolve_token(),
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
    parser.add_argument("--suite", default="trackb", help="Suite name under runs/")
    parser.add_argument("--notes", default="", help="Free text recorded in every manifest of this run")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.set_defaults(func=_cmd)
