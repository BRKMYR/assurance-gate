"""Shared helpers for the workstream A tests. Not a conftest, so no file is shared."""

from __future__ import annotations

from pathlib import Path

from gate.schema import Metrics, Result, Sample

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests/fixtures"
RUNS_FIXTURE = FIXTURES / "runs_fixture"


def make_result(
    scenario_id: str,
    family: str = "cut_in",
    planner: str = "cautious_idm",
    **metrics: object,
) -> Result:
    """Build a Result with the given metrics and simple defaults."""
    parameters = metrics.pop("parameters", {})
    tier = metrics.pop("severity_tier", "nominal")
    return Result(
        scenario_id=scenario_id,
        family=family,
        planner=planner,
        suite="test",
        severity_tier=tier,
        metrics=Metrics(**metrics),
        parameters=parameters,
    )


def make_sample(sample_id: str, task: str = "strong_reject", **fields: object) -> Sample:
    """Build a Sample with simple defaults."""
    base = {"sample_id": sample_id, "task": task, "model": "test/model"}
    base.update(fields)
    return Sample(**base)
