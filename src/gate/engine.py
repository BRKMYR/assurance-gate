"""Gate evaluation and verdict. Binding, see docs/ARCHITECTURE.md sections 3.5, 3.6 and 4.2.

The engine turns public records plus a gate file into one GateOutcome per gate
and one Verdict per candidate. It never reads a file and never touches the
network, so the same inputs always give the same outcomes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from gate.schema import (
    FAMILY_SEVERITY,
    CoverageMatrix,
    Deviation,
    GateOutcome,
    GateSpec,
    RegressionReport,
    Result,
    Sample,
    Verdict,
    WorkedExample,
)
from gate.stats import cp_lower, cp_upper

MAX_FAILING_IDS = 50
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
UNSCORABLE = object()

HEADLINE_FAIL_KEY = "decision.headline"
HEADLINE_PASS_KEY = "decision.headline_pass"
DEFAULT_HEADLINE_FAIL = "{candidate}: {verdict}. {k} of {n} gates failed. {names}."
DEFAULT_HEADLINE_PASS = "{candidate}: GO. {n} of {n} gates passed."

FIXED_WORKED_EXAMPLE = WorkedExample(
    gate_id="a.soft.ttc_cutin",
    n=16,
    n_fail=2,
    point_estimate=0.875,
    bound=0.6165,
    threshold=0.60,
    note_key="gates.worked_example",
    live=False,
)

_PREDICATE_RE = re.compile(
    r"^\s*(?P<field>[A-Za-z_][A-Za-z0-9_.]*)\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<literal>.+?)\s*$"
)


class PredicateError(ValueError):
    """Raised when a gate predicate cannot be parsed."""


@dataclass(frozen=True)
class Predicate:
    """A parsed `field op literal` expression."""

    field: str
    op: str
    literal: Any


def parse_predicate(expression: str) -> Predicate:
    """Parse the small predicate language of spec 4.2."""
    match = _PREDICATE_RE.match(expression or "")
    if match is None:
        raise PredicateError(f"cannot parse predicate {expression!r}")
    return Predicate(match.group("field"), match.group("op"), _parse_literal(match.group("literal")))


def _parse_literal(token: str) -> Any:
    """Turn a literal token into a number, a boolean, None or a string."""
    text = token.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        raise PredicateError(f"cannot parse literal {token!r}") from None


def resolve_field(record: Any, path: str) -> Any:
    """Follow a dotted path on a record. A missing or null field gives UNSCORABLE."""
    current: Any = record
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, None)
        else:
            current = getattr(current, part, None)
        if current is None:
            return UNSCORABLE
    return current


def evaluate_predicate(record: Any, predicate: Predicate) -> bool | None:
    """Return True on pass, False on fail, None when the record is unscorable."""
    if getattr(record, "unscorable", False):
        return None
    value = resolve_field(record, predicate.field)
    if value is UNSCORABLE:
        return None
    literal = predicate.literal
    try:
        if predicate.op == "==":
            return value == literal
        if predicate.op == "!=":
            return value != literal
        if predicate.op == ">=":
            return value >= literal
        if predicate.op == "<=":
            return value <= literal
        if predicate.op == ">":
            return value > literal
        if predicate.op == "<":
            return value < literal
    except TypeError:
        return None
    raise PredicateError(f"unknown operator {predicate.op!r}")


def record_id(record: Any) -> str:
    """Return the public id of a Result or a Sample."""
    return getattr(record, "scenario_id", None) or getattr(record, "sample_id", "")


def select_records(records: Sequence[Any], spec: GateSpec, track: str = "a") -> list[Any]:
    """Select the records a gate applies to, per spec 4.2."""
    if track == "b":
        selected = [r for r in records if getattr(r, "task", None) == spec.family or spec.family == "all"]
        if spec.family == "xstest" and spec.class_ == "availability":
            selected = [r for r in selected if getattr(r, "target_label", None) == "safe"]
        return selected
    if spec.family == "all":
        return list(records)
    return [r for r in records if getattr(r, "family", None) == spec.family]


def _round(value: float | None) -> float | None:
    """Round a float to four decimals, keeping None as None."""
    return None if value is None else round(float(value), 4)


def _parse_time(text: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp with a Z suffix."""
    cleaned = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def waiver_for(waivers: Iterable[Any], gate_id: str, candidate: str) -> Any | None:
    """Return the waiver written for this gate and candidate, or None."""
    for waiver in waivers or []:
        if waiver.gate_id == gate_id and waiver.candidate == candidate:
            return waiver
    return None


def waiver_is_valid(waiver: Any, now_iso: str) -> bool:
    """Return True when a waiver is complete and not expired at `now_iso`."""
    if waiver is None:
        return False
    if not (waiver.signer and waiver.mitigation and waiver.risk_accepted):
        return False
    try:
        return _parse_time(waiver.expires_at) > _parse_time(now_iso)
    except ValueError:
        return False


def deviation_for(deviations: Iterable[Deviation], gate_id: str) -> Deviation | None:
    """Return the deviation written for this gate, or None."""
    for deviation in deviations or []:
        if deviation.gate_id == gate_id:
            return deviation
    return None


def apply_deviation(spec: GateSpec, deviation: Deviation | None, use_frozen: bool = False) -> GateSpec:
    """Return a copy of the gate with the deviated field set, or the gate itself."""
    if deviation is None:
        return spec
    value = deviation.frozen_value if use_frozen else deviation.new_value
    return spec.model_copy(update={deviation.field: value})


def _count_outcome(spec: GateSpec, records: Sequence[Any]) -> dict[str, Any]:
    """Score a count gate and return the raw numbers."""
    predicate = parse_predicate(spec.predicate)
    failing_ids: list[str] = []
    n_unscorable = 0
    n = 0
    for record in records:
        verdict = evaluate_predicate(record, predicate)
        if verdict is None:
            n_unscorable += 1
            continue
        n += 1
        if verdict is False:
            failing_ids.append(record_id(record))
    failing_ids.sort()
    return {
        "n": n,
        "n_fail": len(failing_ids),
        "n_unscorable": n_unscorable,
        "failing_ids": failing_ids[:MAX_FAILING_IDS],
        "point_estimate": None,
        "bound": None,
        "bound_kind": "none",
    }


def _rate_outcome(spec: GateSpec, records: Sequence[Any]) -> dict[str, Any]:
    """Score a rate gate and return the raw numbers with the Clopper Pearson bound."""
    predicate = parse_predicate(spec.predicate)
    passing = 0
    failing_ids: list[str] = []
    n_unscorable = 0
    for record in records:
        verdict = evaluate_predicate(record, predicate)
        if verdict is None:
            n_unscorable += 1
            continue
        if verdict:
            passing += 1
        else:
            failing_ids.append(record_id(record))
    failing_ids.sort()
    n = passing + len(failing_ids)
    if spec.direction == "ceiling":
        k = len(failing_ids)
        bound = cp_upper(k, n) if n else 1.0
        bound_kind = "upper"
    else:
        k = passing
        bound = cp_lower(k, n) if n else 0.0
        bound_kind = "lower"
    return {
        "n": n,
        "n_fail": len(failing_ids),
        "n_unscorable": n_unscorable,
        "failing_ids": failing_ids[:MAX_FAILING_IDS],
        "point_estimate": _round(k / n) if n else None,
        "bound": _round(bound),
        "bound_kind": bound_kind,
    }


def _status_for(spec: GateSpec, numbers: dict[str, Any]) -> tuple[str, float | None]:
    """Return the raw status and margin for a scored gate, before waivers."""
    if spec.kind == "count":
        margin = _round(float(spec.threshold) - numbers["n_fail"])
        return ("pass" if numbers["n_fail"] <= spec.threshold else "fail"), margin
    bound = numbers["bound"]
    if bound is None:
        return "fail", None
    if spec.direction == "ceiling":
        return ("pass" if bound <= spec.threshold else "fail"), _round(spec.threshold - bound)
    return ("pass" if bound >= spec.threshold else "fail"), _round(bound - spec.threshold)


def evaluate_gate(
    spec: GateSpec,
    records: Sequence[Any],
    *,
    candidate: str = "",
    track: str = "a",
    waivers: Sequence[Any] = (),
    deviations: Sequence[Deviation] = (),
    now_iso: str = "1970-01-01T00:00:00Z",
) -> GateOutcome:
    """Evaluate one scored gate (hard, soft or availability) for one candidate."""
    deviation = deviation_for(deviations, spec.id)
    live_spec = apply_deviation(spec, deviation)
    selected = select_records(records, live_spec, track)
    scorer = _count_outcome if live_spec.kind == "count" else _rate_outcome
    numbers = scorer(live_spec, selected)

    reason: str | None = None
    status, margin = _status_for(live_spec, numbers)
    if live_spec.min_n and numbers["n"] < live_spec.min_n:
        status, margin, reason = "fail", None, "insufficient_n"
    elif numbers["n"] == 0 and not live_spec.min_n:
        status, margin, reason = "not_applicable", None, "no_records"

    frozen_status: str | None = None
    if deviation is not None:
        frozen_spec = apply_deviation(spec, deviation, use_frozen=True)
        frozen_selected = select_records(records, frozen_spec, track)
        frozen_scorer = _count_outcome if frozen_spec.kind == "count" else _rate_outcome
        frozen_numbers = frozen_scorer(frozen_spec, frozen_selected)
        frozen_status, _ = _status_for(frozen_spec, frozen_numbers)
        if frozen_spec.min_n and frozen_numbers["n"] < frozen_spec.min_n:
            frozen_status = "fail"

    waiver = waiver_for(waivers, spec.id, candidate)
    waiver_note: str | None = None
    applied_waiver = None
    if waiver is not None:
        if live_spec.class_ in {"hard", "coverage", "regression"}:
            waiver_note = "waiver not permitted"
        elif not waiver_is_valid(waiver, now_iso):
            waiver_note = "waiver expired"
        else:
            applied_waiver = waiver
            if status == "fail":
                status = "conditional"

    return GateOutcome(
        gate_id=spec.id,
        **{"class": live_spec.class_},
        kind=live_spec.kind,
        status=status,
        reason=reason,
        n=numbers["n"],
        n_fail=numbers["n_fail"],
        n_unscorable=numbers["n_unscorable"],
        point_estimate=numbers["point_estimate"],
        bound=numbers["bound"],
        bound_kind=numbers["bound_kind"],
        threshold=float(live_spec.threshold),
        direction=live_spec.direction,
        margin=margin,
        failing_ids=numbers["failing_ids"],
        waiver=applied_waiver if applied_waiver is not None else waiver,
        waiver_note=waiver_note,
        deviation=deviation,
        frozen_status=frozen_status,
    )


def coverage_outcome(spec: GateSpec, matrix: CoverageMatrix) -> GateOutcome:
    """Turn a coverage matrix into the outcome of the coverage gate."""
    empty = [f"{row.family}.{row.parameter}.{row.bin_label}" for row in matrix.rows if row.status == "empty"]
    empty.sort()
    n_fail = len(empty)
    return GateOutcome(
        gate_id=spec.id,
        **{"class": spec.class_},
        kind=spec.kind,
        status="pass" if n_fail <= spec.threshold else "fail",
        reason=None if n_fail <= spec.threshold else "empty_bins",
        n=len(matrix.rows),
        n_fail=n_fail,
        threshold=float(spec.threshold),
        direction=spec.direction,
        margin=_round(float(spec.threshold) - n_fail),
        failing_ids=empty[:MAX_FAILING_IDS],
    )


def regression_outcome(spec: GateSpec, report: RegressionReport | None) -> GateOutcome:
    """Turn a regression report into the outcome of the regression gate."""
    if report is None or report.kind == "comparison":
        return GateOutcome(
            gate_id=spec.id,
            **{"class": spec.class_},
            kind=spec.kind,
            status="not_applicable",
            reason="no_baseline",
            threshold=float(spec.threshold),
            direction=spec.direction,
        )
    n_fail = report.n_tier_worse + report.n_ttc_drop
    failing = sorted(p.scenario_id for p in report.pairs if p.tier_worse or p.ttc_drop)
    return GateOutcome(
        gate_id=spec.id,
        **{"class": spec.class_},
        kind=spec.kind,
        status="pass" if n_fail <= spec.threshold else "fail",
        reason=None if n_fail <= spec.threshold else "regression",
        n=report.n_pairs,
        n_fail=n_fail,
        threshold=float(spec.threshold),
        direction=spec.direction,
        margin=_round(float(spec.threshold) - n_fail),
        failing_ids=failing[:MAX_FAILING_IDS],
    )


def evaluate_all(
    specs: Sequence[GateSpec],
    records: Sequence[Any],
    *,
    candidate: str = "",
    track: str = "a",
    coverage: CoverageMatrix | None = None,
    regression: RegressionReport | None = None,
    waivers: Sequence[Any] = (),
    deviations: Sequence[Deviation] = (),
    now_iso: str = "1970-01-01T00:00:00Z",
) -> list[GateOutcome]:
    """Evaluate every gate in the gate file for one candidate."""
    outcomes: list[GateOutcome] = []
    for spec in specs:
        if spec.class_ == "coverage":
            if coverage is None:
                continue
            outcomes.append(coverage_outcome(spec, coverage))
        elif spec.class_ == "regression":
            outcomes.append(regression_outcome(spec, regression))
        else:
            outcomes.append(
                evaluate_gate(
                    spec,
                    records,
                    candidate=candidate,
                    track=track,
                    waivers=waivers,
                    deviations=deviations,
                    now_iso=now_iso,
                )
            )
    return outcomes


def severity_of(spec: GateSpec) -> str:
    """Return the severity used for ordering, the family table wins where it applies."""
    return FAMILY_SEVERITY.get(spec.family, spec.severity)


def order_failing(outcomes: Sequence[GateOutcome], specs: Sequence[GateSpec]) -> list[str]:
    """Order failing gates: hard first, then severity high to low, then id."""
    by_id = {spec.id: spec for spec in specs}

    def key(outcome: GateOutcome) -> tuple[int, int, str]:
        spec = by_id.get(outcome.gate_id)
        severity = severity_of(spec) if spec is not None else "medium"
        is_hard = 0 if outcome.class_ == "hard" else 1
        return (is_hard, SEVERITY_RANK.get(severity, 1), outcome.gate_id)

    return [o.gate_id for o in sorted([o for o in outcomes if o.status == "fail"], key=key)]


def build_verdict(
    outcomes: Sequence[GateOutcome],
    specs: Sequence[GateSpec],
    *,
    candidate: str,
    suite: str,
    strings: dict[str, str] | None = None,
) -> Verdict:
    """Apply the verdict algorithm of spec 3.6 and render the headline."""
    strings = strings or {}
    failing = order_failing(outcomes, specs)
    conditional = sorted(o.gate_id for o in outcomes if o.status == "conditional")
    by_id = {o.gate_id: o for o in outcomes}

    blocking = {"hard", "coverage", "regression"}
    label = "GO"
    if any(by_id[g].class_ in blocking for g in failing):
        label = "NO_GO"
    elif failing:
        label = "NO_GO"
    elif conditional:
        label = "CONDITIONAL"

    n_gates = len(outcomes)
    if failing:
        names = ", ".join(strings.get(f"gate.short.{gid}", gid) for gid in failing)
        template = strings.get(HEADLINE_FAIL_KEY, DEFAULT_HEADLINE_FAIL)
        headline = template.format(candidate=candidate, verdict=label, k=len(failing), n=n_gates, names=names)
    else:
        template = strings.get(HEADLINE_PASS_KEY, DEFAULT_HEADLINE_PASS)
        headline = template.format(candidate=candidate, verdict=label, k=0, n=n_gates, names="")
    return Verdict(
        candidate=candidate,
        suite=suite,
        verdict=label,
        failing_gates=failing,
        conditional_gates=conditional,
        n_gates=n_gates,
        headline=headline,
    )


def worked_example(outcomes: Sequence[GateOutcome]) -> WorkedExample:
    """Find a rate gate where the point estimate and the bound disagree, else the fixed example."""
    for outcome in outcomes:
        if outcome.kind != "rate" or outcome.point_estimate is None or outcome.bound is None:
            continue
        if outcome.direction == "ceiling":
            by_point = outcome.point_estimate <= outcome.threshold
            by_bound = outcome.bound <= outcome.threshold
        else:
            by_point = outcome.point_estimate >= outcome.threshold
            by_bound = outcome.bound >= outcome.threshold
        if by_point != by_bound:
            return WorkedExample(
                gate_id=outcome.gate_id,
                n=outcome.n,
                n_fail=outcome.n_fail,
                point_estimate=outcome.point_estimate,
                bound=outcome.bound,
                threshold=outcome.threshold,
                note_key="gates.worked_example",
                live=True,
            )
    return FIXED_WORKED_EXAMPLE.model_copy()


__all__ = [
    "MAX_FAILING_IDS",
    "FIXED_WORKED_EXAMPLE",
    "Predicate",
    "PredicateError",
    "parse_predicate",
    "evaluate_predicate",
    "resolve_field",
    "select_records",
    "evaluate_gate",
    "coverage_outcome",
    "regression_outcome",
    "evaluate_all",
    "order_failing",
    "build_verdict",
    "worked_example",
    "waiver_is_valid",
    "Result",
    "Sample",
]
