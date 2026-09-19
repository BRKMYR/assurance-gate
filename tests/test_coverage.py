"""Coverage tests. Spec section 5, acceptance test AC-8."""

from __future__ import annotations

from gate.coverage import bin_index, build_coverage, build_coverage_b, load_bins_config, row_status
from gate.engine import coverage_outcome
from gate.schema import GateSpec

from helpers_a import REPO, make_result, make_sample


def coverage_spec() -> GateSpec:
    """Return the coverage gate specification."""
    return GateSpec(
        id="a.cov.bins",
        **{"class": "coverage"},
        kind="count",
        family="all",
        predicate="",
        threshold=0,
        direction="max",
        severity="medium",
        min_n=0,
        rationale="[[OWNER_COPY: rationale a.cov.bins]]",
        source="UL 4600:2023 Section 8 (informative)",
    )


def small_config() -> dict:
    """Return a one family, one parameter bin configuration."""
    return {
        "families": {"cut_in": {"ego_speed_mps": [15.0, 17.33, 19.67, 22.0]}},
        "absolute_value_parameters": ["brake_decel_mps2"],
        "not_covered": [{"hazard": "intersections", "note_key": "coverage.not_covered.intersections"}],
    }


def test_bin_index_last_bin_is_closed_on_the_right() -> None:
    edges = [15.0, 17.33, 19.67, 22.0]
    assert bin_index(15.0, edges) == 0
    assert bin_index(17.33, edges) == 1
    assert bin_index(19.67, edges) == 2
    assert bin_index(22.0, edges) == 2
    assert bin_index(22.1, edges) is None
    assert bin_index(14.9, edges) is None


def test_row_status_thresholds() -> None:
    assert row_status(0) == "empty"
    assert row_status(1) == "sparse"
    assert row_status(2) == "ok"


def test_ac_8_one_empty_bin_fails_the_coverage_gate() -> None:
    results = [
        make_result("c1", parameters={"ego_speed_mps": 16.0}),
        make_result("c2", parameters={"ego_speed_mps": 16.5}),
        make_result("c3", parameters={"ego_speed_mps": 18.0}),
        make_result("c4", parameters={"ego_speed_mps": 18.5}),
    ]
    matrix = build_coverage(results, small_config())
    assert [row.status for row in matrix.rows] == ["ok", "ok", "empty"]
    assert matrix.passed is False
    outcome = coverage_outcome(coverage_spec(), matrix)
    assert outcome.status == "fail"
    assert outcome.n_fail == 1


def test_ac_8_full_bins_pass_and_not_covered_rows_never_gate() -> None:
    results = [
        make_result("c1", parameters={"ego_speed_mps": 16.0}),
        make_result("c2", parameters={"ego_speed_mps": 16.5}),
        make_result("c3", parameters={"ego_speed_mps": 18.0}),
        make_result("c4", parameters={"ego_speed_mps": 18.5}),
        make_result("c5", parameters={"ego_speed_mps": 21.0}),
        make_result("c6", parameters={"ego_speed_mps": 21.5}),
    ]
    matrix = build_coverage(results, small_config())
    assert matrix.passed is True
    assert coverage_outcome(coverage_spec(), matrix).status == "pass"
    assert [row.hazard for row in matrix.not_covered] == ["intersections"]


def test_sparse_bins_are_amber_and_never_gate() -> None:
    results = [
        make_result("c1", parameters={"ego_speed_mps": 16.0}),
        make_result("c2", parameters={"ego_speed_mps": 18.0}),
        make_result("c3", parameters={"ego_speed_mps": 21.0}),
    ]
    matrix = build_coverage(results, small_config())
    assert [row.status for row in matrix.rows] == ["sparse", "sparse", "sparse"]
    assert matrix.passed is True


def test_missing_or_out_of_range_parameters_count_as_unbinned() -> None:
    results = [
        make_result("c1", parameters={"ego_speed_mps": None}),
        make_result("c2", parameters={}),
        make_result("c3", parameters={"ego_speed_mps": 99.0}),
    ]
    matrix = build_coverage(results, small_config())
    assert matrix.unbinned == 3


def test_absolute_value_parameter_is_binned_on_its_magnitude() -> None:
    config = {
        "families": {"hard_brake": {"brake_decel_mps2": [3.5, 5.0, 6.5, 8.0]}},
        "absolute_value_parameters": ["brake_decel_mps2"],
        "not_covered": [],
    }
    results = [make_result("h1", family="hard_brake", parameters={"brake_decel_mps2": -4.56})]
    matrix = build_coverage(results, config)
    assert matrix.rows[0].n == 1
    assert matrix.rows[0].scenario_ids == ["h1"]


def test_repo_bin_edges_match_the_binding_table() -> None:
    repo = REPO
    config = load_bins_config(repo / "configs/coverage_bins.yaml")
    families = config["families"]
    assert families["cut_in"]["ego_speed_mps"] == [15.0, 17.33, 19.67, 22.0]
    assert families["cut_in"]["initial_gap_m"] == [15, 20, 25, 30]
    assert families["cut_in"]["trigger_gap_m"] == [8.0, 11.33, 14.67, 18.0]
    assert families["ped_occluded"]["ego_speed_mps"] == [8.0, 10.0, 12.0, 14.0]
    assert families["ped_occluded"]["occluder_x_m"] == [40, 50, 60, 70]
    assert families["ped_occluded"]["ped_speed_mps"] == [1.0, 1.5, 2.0, 2.5]
    assert families["weather_ramp"]["ego_speed_mps"] == [14, 16, 18, 20]
    assert families["weather_ramp"]["visibility_end_m"] == [15, 25, 35, 45]
    assert families["weather_ramp"]["friction_end"] == [0.25, 0.3333, 0.4167, 0.5]
    assert families["hard_brake"]["ego_speed_mps"] == [15.0, 17.33, 19.67, 22.0]
    assert families["hard_brake"]["initial_gap_m"] == [12.0, 19.67, 27.33, 35.0]
    assert families["hard_brake"]["brake_decel_mps2"] == [3.5, 5.0, 6.5, 8.0]
    hazards = [row["hazard"] for row in config["not_covered"]]
    assert hazards == [
        "intersections",
        "cyclists",
        "night and low light",
        "sensor faults",
        "multi actor interactions",
        "ODD exit behaviour",
    ]


def test_track_b_coverage_flags_an_empty_hazard_and_unmapped_categories() -> None:
    hazards = [
        {"id": "violent_crimes", "maps_to": ["violence", "weapons"]},
        {"id": "self_harm", "maps_to": ["self_harm"]},
    ]
    samples = [
        make_sample("s1", category="violence"),
        make_sample("s2", category="Weapons"),
        make_sample("s3", category="mystery"),
    ]
    matrix = build_coverage_b(samples, hazards)
    by_hazard = {row.parameter: row for row in matrix.rows}
    assert by_hazard["violent_crimes"].n == 2
    assert by_hazard["self_harm"].status == "empty"
    assert matrix.passed is False
    assert matrix.unmapped == ["mystery"]
