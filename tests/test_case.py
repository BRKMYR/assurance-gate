"""Assurance case and residual risk tests. Spec section 3.10."""

from __future__ import annotations

from gate.case import DEFEATERS, RISK_ITEMS, build_case, build_residual_risk, worst_result
from gate.coverage import build_coverage
from gate.engine import evaluate_gate
from gate.schema import GateSpec

from helpers_a import make_result


def hard_spec() -> GateSpec:
    """Return the pedestrian collision gate."""
    return GateSpec(
        id="a.hard.ped_collision",
        **{"class": "hard"},
        kind="count",
        family="ped_occluded",
        predicate="metrics.collision == false",
        threshold=0,
        direction="max",
        severity="high",
        min_n=0,
        rationale="[[OWNER_COPY: rationale a.hard.ped_collision]]",
        source="ISO 21448:2022 clause 7 (informative)",
    )


def sample_results() -> list:
    """Return two pedestrian results, one of them a collision."""
    return [
        make_result("p1", family="ped_occluded", collision=True, severity_tier="critical", ttc_min_s=0.2),
        make_result("p2", family="ped_occluded", collision=False, severity_tier="nominal", ttc_min_s=5.0),
    ]


def build_tree() -> dict:
    """Build the case tree for the sample results."""
    results = sample_results()
    outcome = evaluate_gate(hard_spec(), results)
    return build_case([outcome], results, gate_family={"a.hard.ped_collision": "ped_occluded"})


def test_tree_root_and_goal_key() -> None:
    tree = build_tree()
    assert tree["root"] == "g0"
    nodes = {node["id"]: node for node in tree["nodes"]}
    assert nodes["g0"]["type"] == "goal"
    assert nodes["g0"]["text_key"] == "case.goal"


def test_two_contexts_one_of_them_the_deployment_slot() -> None:
    nodes = build_tree()["nodes"]
    contexts = [n for n in nodes if n["type"] == "context"]
    assert len(contexts) == 2
    assert {n["text_key"] for n in contexts} == {"case.context.engine_limits", "owner.deployment_context"}


def test_assumptions_and_one_strategy() -> None:
    nodes = build_tree()["nodes"]
    assert len([n for n in nodes if n["type"] == "assumption"]) == 3
    strategies = [n for n in nodes if n["type"] == "strategy"]
    assert len(strategies) == 1
    assert strategies[0]["children"] == ["cl.ped_occluded"]


def test_one_claim_per_family_carries_the_gate_status() -> None:
    nodes = {n["id"]: n for n in build_tree()["nodes"]}
    claim = nodes["cl.ped_occluded"]
    assert claim["type"] == "claim"
    assert claim["text_key"] == "case.claim.ped_occluded"
    assert claim["status"] == "fail"


def test_evidence_leaves_cover_failing_ids_and_the_worst_record() -> None:
    nodes = {n["id"]: n for n in build_tree()["nodes"]}
    assert nodes["ev.ped_occluded.p1"]["status"] == "fail"
    assert nodes["ev.ped_occluded.p1"]["evidence_ref"] == "p1"
    assert nodes["ev.gate.ped_occluded.a.hard.ped_collision"]["evidence_ref"] == "a.hard.ped_collision"


def test_worst_result_prefers_the_highest_tier_then_the_lowest_ttc() -> None:
    results = sample_results()
    assert worst_result(results).scenario_id == "p1"
    assert worst_result([]) is None


def test_four_defeaters_with_the_binding_keys() -> None:
    nodes = build_tree()["nodes"]
    keys = sorted(n["text_key"] for n in nodes if n["type"] == "defeater")
    assert keys == sorted(f"case.defeater.{name}" for name in DEFEATERS)
    assert sorted(DEFEATERS) == ["contamination", "quantisation", "sandbagging", "unknown_unsafe"]


def test_residual_risk_rows_carry_the_four_items_and_the_not_covered_hazards() -> None:
    results = sample_results()
    coverage = build_coverage(
        results,
        {
            "families": {"ped_occluded": {"ego_speed_mps": [8.0, 10.0, 12.0, 14.0]}},
            "absolute_value_parameters": [],
            "not_covered": [{"hazard": "cyclists", "note_key": "coverage.not_covered.cyclists"}],
        },
    )
    rows = build_residual_risk(results, coverage)
    assert len(rows) == 1
    assert rows[0].family == "ped_occluded"
    assert rows[0].cannot_see == [f"risk.ped_occluded.{item}" for item in RISK_ITEMS]
    assert rows[0].not_covered == ["cyclists"]


def test_node_ids_are_unique() -> None:
    nodes = build_tree()["nodes"]
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids))
