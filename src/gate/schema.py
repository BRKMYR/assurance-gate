"""Every data contract in assurance-gate. Binding, see docs/ARCHITECTURE.md section 3.

Nothing else defines data shapes. Adapters produce these, the engine consumes
them, the build serialises them. Public records forbid extra fields so that a
private field such as `trajectory_log` can never leak into an output file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

Track = Literal["a", "b"]
GateClass = Literal["hard", "soft", "coverage", "regression", "availability"]
GateKind = Literal["count", "rate"]
Direction = Literal["max", "floor", "ceiling"]
Severity = Literal["high", "medium", "low"]
Status = Literal["pass", "fail", "conditional", "not_applicable"]
VerdictLabel = Literal["GO", "NO_GO", "CONDITIONAL"]
Tier = Literal["nominal", "near_miss", "critical"]
BinStatus = Literal["empty", "sparse", "ok"]
NodeType = Literal["goal", "context", "assumption", "strategy", "claim", "evidence", "defeater"]
NodeStatus = Literal["pass", "fail", "conditional", "info"]

TIER_ORDER: dict[str, int] = {"nominal": 0, "near_miss": 1, "critical": 2}
FAMILY_SEVERITY: dict[str, Severity] = {
    "ped_occluded": "high",
    "cut_in": "medium",
    "hard_brake": "medium",
    "weather_ramp": "medium",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


# 3.1 Manifest ---------------------------------------------------------------


class PublishedAt(_Strict):
    github_release: str | None = None
    hf_dataset_commit: str | None = None


class ToolVersions(_Strict):
    avsb: str | None = None
    gate: str | None = None
    inspect_ai: str | None = None
    inspect_evals: str | None = None
    judge_prompt_version: str | None = None


class Manifest(_Strict):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    suite: str
    track: Track
    candidate: str
    baseline: str | None = None
    generated_at: str
    preregistered: bool
    gate_file: str
    gate_file_sha256: str
    gate_published_at: PublishedAt | None = None
    seed: int = 0
    tools: ToolVersions = Field(default_factory=ToolVersions)
    n_results: int = 0
    notes: str = ""


# 3.2 Result (Track A public record) -----------------------------------------


class Metrics(_Strict):
    ttc_min_s: float | None = None
    ttc_min_t_s: float | None = None
    pet_min_s: float | None = None
    d_min_m: float | None = None
    d_min_t_s: float | None = None
    collision: bool | None = None
    collision_t_s: float | None = None
    delta_v_mps: float | None = None
    severity_index: int | None = None
    hard_brake_events: int | None = None
    hard_brake_fraction: float | None = None
    mean_speed_ratio: float | None = None


class Result(_Strict):
    scenario_id: str
    family: str
    planner: str
    suite: str
    duration_s: float | None = None
    n_steps: int | None = None
    score: float | None = None
    severity_tier: Tier | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    parameters: dict[str, float | None] = Field(default_factory=dict)
    description: str = ""
    thumbnail: str | None = None


# 3.3 Sample (Track B public record) -----------------------------------------


class Sample(_Strict):
    sample_id: str
    task: str
    model: str
    category: str | None = None
    target_label: str | None = None
    score: float | None = None
    compliant: bool | None = None
    refused: bool | None = None
    unscorable: bool = False
    completion_public: str = ""
    inspect_ref: str | None = None


# 3.4 Gate specification -----------------------------------------------------


class GateSpec(_Strict):
    id: str
    class_: GateClass = Field(alias="class")
    kind: GateKind
    family: str = "all"          # Track A family or "all"; Track B task name
    predicate: str = ""
    threshold: float
    direction: Direction
    severity: Severity
    min_n: int = 0
    rationale: str
    source: str
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Binarisation(_Strict):
    compliant_if_score_gte: float = 0.5


class GateFile(_Strict):
    schema_version: str = SCHEMA_VERSION
    track: Track
    suite: str
    frozen: bool = False
    binarisation: dict[str, Binarisation] = Field(default_factory=dict)
    gates: list[GateSpec]


# 3.7 Waiver and Deviation ---------------------------------------------------


class Waiver(_Strict):
    gate_id: str
    candidate: str
    signer: str
    risk_accepted: str
    mitigation: str
    expires_at: str


class Deviation(_Strict):
    gate_id: str
    field: str
    frozen_value: float | str | bool
    new_value: float | str | bool
    reason: str
    changed_at: str
    signer: str


# 3.5 GateOutcome and 3.6 Verdict --------------------------------------------


class GateOutcome(_Strict):
    gate_id: str
    class_: GateClass = Field(alias="class")
    kind: GateKind
    status: Status
    reason: str | None = None            # for example "insufficient_n"
    n: int = 0
    n_fail: int = 0
    n_unscorable: int = 0
    point_estimate: float | None = None
    bound: float | None = None
    bound_kind: Literal["lower", "upper", "none"] = "none"
    threshold: float
    direction: Direction
    margin: float | None = None
    failing_ids: list[str] = Field(default_factory=list)
    waiver: Waiver | None = None
    waiver_note: str | None = None       # "waiver not permitted" or "waiver expired"
    deviation: Deviation | None = None
    frozen_status: Status | None = None
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Verdict(_Strict):
    candidate: str
    suite: str
    verdict: VerdictLabel
    failing_gates: list[str] = Field(default_factory=list)
    conditional_gates: list[str] = Field(default_factory=list)
    n_gates: int = 0
    headline: str = ""


# 3.8 Coverage ---------------------------------------------------------------


class CoverageRow(_Strict):
    family: str
    parameter: str
    bin_label: str
    lo: float
    hi: float
    n: int
    status: BinStatus
    scenario_ids: list[str] = Field(default_factory=list)


class NotCoveredRow(_Strict):
    hazard: str
    note_key: str


class CoverageMatrix(_Strict):
    track: Track
    rows: list[CoverageRow] = Field(default_factory=list)
    unbinned: int = 0
    unmapped: list[str] = Field(default_factory=list)   # Track B categories with no hazard
    not_covered: list[NotCoveredRow] = Field(default_factory=list)
    passed: bool = True


# 3.9 Regression -------------------------------------------------------------


class PairDelta(_Strict):
    scenario_id: str
    family: str
    tier_baseline: Tier | None = None
    tier_candidate: Tier | None = None
    ttc_baseline: float | None = None
    ttc_candidate: float | None = None
    ttc_delta: float | None = None
    tier_worse: bool = False
    ttc_drop: bool = False


class RegressionReport(_Strict):
    candidate: str
    baseline: str
    kind: Literal["regression", "comparison"] = "regression"
    pairs: list[PairDelta] = Field(default_factory=list)
    n_pairs: int = 0
    n_tier_worse: int = 0
    n_ttc_drop: int = 0
    family_means: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    passed: bool | None = None


# 3.10 Assurance case --------------------------------------------------------


class CaseNode(_Strict):
    id: str
    type: NodeType
    text_key: str
    children: list[str] = Field(default_factory=list)
    evidence_ref: str | None = None
    status: NodeStatus = "info"


class ResidualRiskRow(_Strict):
    family: str
    cannot_see: list[str] = Field(default_factory=list)
    not_covered: list[str] = Field(default_factory=list)


# 3.11 data.json envelope ----------------------------------------------------


class WorkedExample(_Strict):
    gate_id: str
    n: int
    n_fail: int
    point_estimate: float
    bound: float
    threshold: float
    note_key: str = "gates.worked_example"
    live: bool = False


class CandidateBlock(_Strict):
    candidate: str
    baseline: str | None = None
    verdict: Verdict
    gates: list[GateOutcome] = Field(default_factory=list)
    coverage: CoverageMatrix
    regression: RegressionReport | None = None
    case: dict = Field(default_factory=dict)          # {"nodes": [CaseNode], "root": id}
    residual_risk: list[ResidualRiskRow] = Field(default_factory=list)
    worked_example: WorkedExample
    results: list[Result] = Field(default_factory=list)
    samples: list[Sample] = Field(default_factory=list)
    excluded: bool = False


class SuiteBlock(_Strict):
    suite: str
    preregistered: bool
    gate_file_sha256: str
    gate_published_at: PublishedAt | None = None
    first_run_at: str | None = None
    credibility: list[str] = Field(default_factory=list)
    independence: list[str] = Field(default_factory=list)
    deviations: list[Deviation] = Field(default_factory=list)
    candidates: list[CandidateBlock] = Field(default_factory=list)


class DataFile(_Strict):
    schema_version: str = SCHEMA_VERSION
    built_with: str
    track: Track
    bundle: str | None = None
    suites: list[SuiteBlock] = Field(default_factory=list)


__all__ = [name for name in dir() if name[:1].isupper()] + ["SCHEMA_VERSION", "TIER_ORDER", "FAMILY_SEVERITY"]
