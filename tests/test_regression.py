"""Paired regression tests. Spec section 6, acceptance test AC-9."""

from __future__ import annotations

from gate.engine import regression_outcome
from gate.regression import build_comparison_b, build_regression, tier_worse, ttc_drop
from gate.schema import GateSpec

from helpers_a import make_result, make_sample


def regression_spec() -> GateSpec:
    """Return the regression gate specification."""
    return GateSpec(
        id="a.reg.paired",
        **{"class": "regression"},
        kind="count",
        family="all",
        predicate="",
        threshold=0,
        direction="max",
        severity="medium",
        min_n=0,
        rationale="[[OWNER_COPY: rationale a.reg.paired]]",
        source="ISO 21448:2022 Annex C (informative)",
    )


def test_ac_9_tier_getting_worse_counts() -> None:
    candidate = [make_result("s1", severity_tier="critical", ttc_min_s=2.0)]
    baseline = [make_result("s1", planner="idm", severity_tier="near_miss", ttc_min_s=2.0)]
    report = build_regression(candidate, baseline, candidate="cautious_idm", baseline="idm")
    assert report.n_pairs == 1
    assert report.n_tier_worse == 1
    assert report.passed is False
    assert regression_outcome(regression_spec(), report).status == "fail"


def test_ac_9_a_ttc_drop_of_zero_point_four_does_not_count() -> None:
    candidate = [make_result("s1", ttc_min_s=2.6)]
    baseline = [make_result("s1", planner="idm", ttc_min_s=3.0)]
    report = build_regression(candidate, baseline, candidate="c", baseline="idm")
    assert report.n_ttc_drop == 0
    assert report.passed is True


def test_ac_9_a_ttc_drop_of_zero_point_six_counts() -> None:
    candidate = [make_result("s1", ttc_min_s=2.4)]
    baseline = [make_result("s1", planner="idm", ttc_min_s=3.0)]
    report = build_regression(candidate, baseline, candidate="c", baseline="idm")
    assert report.n_ttc_drop == 1
    assert report.pairs[0].ttc_delta == -0.6
    assert report.passed is False


def test_ac_9_null_ttc_never_counts() -> None:
    candidate = [make_result("s1")]
    baseline = [make_result("s1", planner="idm", ttc_min_s=3.0)]
    report = build_regression(candidate, baseline, candidate="c", baseline="idm")
    assert report.n_ttc_drop == 0
    assert report.pairs[0].ttc_delta is None


def test_tier_order_helpers() -> None:
    assert tier_worse("nominal", "near_miss") is True
    assert tier_worse("critical", "nominal") is False
    assert tier_worse(None, "critical") is False
    assert ttc_drop(3.0, 2.5) is False
    assert ttc_drop(3.0, 2.49) is True
    assert ttc_drop(None, 1.0) is False


def test_unpaired_scenarios_are_dropped_and_family_means_are_reported() -> None:
    candidate = [make_result("s1", ttc_min_s=2.0), make_result("s2", ttc_min_s=4.0)]
    baseline = [make_result("s1", planner="idm", ttc_min_s=2.2)]
    report = build_regression(candidate, baseline, candidate="c", baseline="idm")
    assert report.n_pairs == 1
    assert report.family_means["cut_in"]["ttc_candidate"] == 2.0


def test_no_baseline_makes_the_regression_gate_not_applicable() -> None:
    assert regression_outcome(regression_spec(), None).status == "not_applicable"


def test_track_b_comparison_never_gates() -> None:
    candidate = [make_sample("s1", compliant=True, score=0.9)]
    baseline = [make_sample("s1", compliant=False, score=0.1)]
    report = build_comparison_b(candidate, baseline, candidate="model_a", baseline="model_b")
    assert report.kind == "comparison"
    assert report.passed is None
    assert report.n_tier_worse == 1
    assert regression_outcome(regression_spec(), report).status == "not_applicable"
