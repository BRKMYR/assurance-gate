"""Assurance case tree and residual risk. Binding, see docs/ARCHITECTURE.md section 3.10.

The tree is a small goal structure. One goal, two contexts, a few assumptions,
one strategy, one claim per family, evidence leaves under each claim and four
defeaters that say what would break the argument. Every text lives in
`strings.json`, this module only writes keys.
"""

from __future__ import annotations

from typing import Any, Sequence

from gate.schema import TIER_ORDER, CaseNode, CoverageMatrix, GateOutcome, ResidualRiskRow

GOAL_ID = "g0"
GOAL_KEY = "case.goal"
CONTEXT_ENGINE_KEY = "case.context.engine_limits"
CONTEXT_DEPLOYMENT_KEY = "owner.deployment_context"
STRATEGY_KEY = "case.strategy"
ASSUMPTIONS = ("simulation_fidelity", "predicate_validity", "baseline_comparable")
DEFEATERS = ("contamination", "quantisation", "sandbagging", "unknown_unsafe")
RISK_ITEMS = ("perception", "latency", "multi_actor", "odd_exit")


def _claim_status(outcomes: Sequence[GateOutcome]) -> str:
    """Return the status of a claim from the gates that support it."""
    if not outcomes:
        return "info"
    if any(o.status == "fail" for o in outcomes):
        return "fail"
    if any(o.status == "conditional" for o in outcomes):
        return "conditional"
    if all(o.status == "not_applicable" for o in outcomes):
        return "info"
    return "pass"


def worst_result(results: Sequence[Any]) -> Any | None:
    """Return the worst result of a family: highest tier first, then lowest time to collision."""
    if not results:
        return None

    def key(result: Any) -> tuple[int, float, str]:
        tier = TIER_ORDER.get(result.severity_tier or "nominal", 0)
        ttc = getattr(result.metrics, "ttc_min_s", None)
        ttc_key = float(ttc) if isinstance(ttc, (int, float)) else float("inf")
        return (-tier, ttc_key, result.scenario_id)

    return sorted(results, key=key)[0]


def build_case(
    outcomes: Sequence[GateOutcome],
    results: Sequence[Any],
    *,
    track: str = "a",
    hazards: Sequence[str] = (),
    gate_family: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the assurance case tree and return `{"nodes": [...], "root": "g0"}`."""
    gate_family = gate_family or {}
    nodes: list[CaseNode] = []

    if track == "b":
        groups = list(hazards)
    else:
        groups = sorted({getattr(r, "family", "") for r in results if getattr(r, "family", None)})
        if not groups:
            groups = sorted({f for f in gate_family.values() if f and f != "all"})

    context_ids = ["c.engine_limits", "c.deployment"]
    assumption_ids = [f"a.{name}" for name in ASSUMPTIONS]
    strategy_id = "s0"
    defeater_ids = [f"d.{name}" for name in DEFEATERS]

    nodes.append(
        CaseNode(
            id=GOAL_ID,
            type="goal",
            text_key=GOAL_KEY,
            children=context_ids + assumption_ids + [strategy_id] + defeater_ids,
            status=_claim_status(outcomes),
        )
    )
    nodes.append(CaseNode(id=context_ids[0], type="context", text_key=CONTEXT_ENGINE_KEY))
    nodes.append(CaseNode(id=context_ids[1], type="context", text_key=CONTEXT_DEPLOYMENT_KEY))
    for name, node_id in zip(ASSUMPTIONS, assumption_ids):
        nodes.append(CaseNode(id=node_id, type="assumption", text_key=f"case.assumption.{name}"))

    claim_ids: list[str] = []
    claim_nodes: list[CaseNode] = []
    evidence_nodes: list[CaseNode] = []
    for group in groups:
        claim_id = f"cl.{group}"
        claim_ids.append(claim_id)
        related = [o for o in outcomes if gate_family.get(o.gate_id, "all") in {group, "all"}]
        children: list[str] = []
        for outcome in related:
            node_id = f"ev.gate.{group}.{outcome.gate_id}"
            children.append(node_id)
            evidence_nodes.append(
                CaseNode(
                    id=node_id,
                    type="evidence",
                    text_key=f"gate.short.{outcome.gate_id}",
                    evidence_ref=outcome.gate_id,
                    status="info" if outcome.status == "not_applicable" else outcome.status,
                )
            )
        group_results = [r for r in results if getattr(r, "family", None) == group]
        failing_ids: list[str] = []
        for outcome in related:
            failing_ids.extend(
                rid for rid in outcome.failing_ids if any(getattr(r, "scenario_id", getattr(r, "sample_id", "")) == rid for r in group_results)
            )
        worst = worst_result(group_results) if track == "a" else None
        record_ids = sorted(set(failing_ids))
        if worst is not None and worst.scenario_id not in record_ids:
            record_ids.append(worst.scenario_id)
        for record_id in record_ids:
            node_id = f"ev.{group}.{record_id}"
            children.append(node_id)
            evidence_nodes.append(
                CaseNode(
                    id=node_id,
                    type="evidence",
                    text_key="case.evidence.record",
                    evidence_ref=record_id,
                    status="fail" if record_id in failing_ids else "info",
                )
            )
        claim_nodes.append(
            CaseNode(
                id=claim_id,
                type="claim",
                text_key=f"case.claim.{group}",
                children=children,
                status=_claim_status(related),
            )
        )

    nodes.append(CaseNode(id=strategy_id, type="strategy", text_key=STRATEGY_KEY, children=claim_ids))
    nodes.extend(claim_nodes)
    nodes.extend(evidence_nodes)
    for name, node_id in zip(DEFEATERS, defeater_ids):
        nodes.append(CaseNode(id=node_id, type="defeater", text_key=f"case.defeater.{name}"))

    return {"nodes": [node.model_dump() for node in nodes], "root": GOAL_ID}


def build_residual_risk(
    results: Sequence[Any],
    coverage: CoverageMatrix | None = None,
    *,
    families: Sequence[str] = (),
) -> list[ResidualRiskRow]:
    """Build one residual risk row per family, with the not covered hazards on every row."""
    names = sorted({getattr(r, "family", "") for r in results if getattr(r, "family", None)}) or sorted(families)
    not_covered = [row.hazard for row in (coverage.not_covered if coverage else [])]
    return [
        ResidualRiskRow(
            family=family,
            cannot_see=[f"risk.{family}.{item}" for item in RISK_ITEMS],
            not_covered=not_covered,
        )
        for family in names
    ]


__all__ = [
    "GOAL_ID",
    "ASSUMPTIONS",
    "DEFEATERS",
    "RISK_ITEMS",
    "worst_result",
    "build_case",
    "build_residual_risk",
]
