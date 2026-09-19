"""Paired regression against the baseline. Binding, see docs/ARCHITECTURE.md section 6.

Results are paired by scenario id inside one suite. A pair is a regression when
the severity tier gets worse or when the time to collision drops by more than
half a second. Family means are for display and never gate.
"""

from __future__ import annotations

from typing import Any, Sequence

from gate.schema import TIER_ORDER, PairDelta, RegressionReport

TTC_DROP_S = 0.5


def _round(value: float | None) -> float | None:
    """Round a float to four decimals, keeping None as None."""
    return None if value is None else round(float(value), 4)


def _finite(value: Any) -> bool:
    """Return True when a metric is a usable number."""
    return isinstance(value, (int, float)) and value == value and abs(float(value)) != float("inf")


def tier_worse(baseline: str | None, candidate: str | None) -> bool:
    """Return True when the candidate tier sits later in the tier order."""
    if baseline is None or candidate is None:
        return False
    return TIER_ORDER.get(candidate, -1) > TIER_ORDER.get(baseline, -1)


def ttc_drop(baseline: Any, candidate: Any) -> bool:
    """Return True when the candidate time to collision drops by more than half a second."""
    if not (_finite(baseline) and _finite(candidate)):
        return False
    return float(candidate) < float(baseline) - TTC_DROP_S


def _family_means(pairs: Sequence[PairDelta]) -> dict[str, dict[str, float | None]]:
    """Return mean baseline and candidate time to collision per family, for display."""
    means: dict[str, dict[str, float | None]] = {}
    families = sorted({pair.family for pair in pairs})
    for family in families:
        rows = [p for p in pairs if p.family == family]
        base = [p.ttc_baseline for p in rows if _finite(p.ttc_baseline)]
        cand = [p.ttc_candidate for p in rows if _finite(p.ttc_candidate)]
        means[family] = {
            "ttc_baseline": _round(sum(base) / len(base)) if base else None,
            "ttc_candidate": _round(sum(cand) / len(cand)) if cand else None,
            "n_pairs": float(len(rows)),
        }
    return means


def build_regression(
    candidate_results: Sequence[Any],
    baseline_results: Sequence[Any],
    *,
    candidate: str,
    baseline: str,
) -> RegressionReport:
    """Pair the candidate and the baseline by scenario id and score every pair."""
    base_by_id = {r.scenario_id: r for r in baseline_results}
    pairs: list[PairDelta] = []
    for result in sorted(candidate_results, key=lambda r: r.scenario_id):
        other = base_by_id.get(result.scenario_id)
        if other is None:
            continue
        ttc_base = getattr(other.metrics, "ttc_min_s", None)
        ttc_cand = getattr(result.metrics, "ttc_min_s", None)
        delta = _round(ttc_cand - ttc_base) if _finite(ttc_base) and _finite(ttc_cand) else None
        pairs.append(
            PairDelta(
                scenario_id=result.scenario_id,
                family=result.family,
                tier_baseline=other.severity_tier,
                tier_candidate=result.severity_tier,
                ttc_baseline=_round(ttc_base),
                ttc_candidate=_round(ttc_cand),
                ttc_delta=delta,
                tier_worse=tier_worse(other.severity_tier, result.severity_tier),
                ttc_drop=ttc_drop(ttc_base, ttc_cand),
            )
        )
    n_tier_worse = sum(1 for p in pairs if p.tier_worse)
    n_ttc_drop = sum(1 for p in pairs if p.ttc_drop)
    return RegressionReport(
        candidate=candidate,
        baseline=baseline,
        kind="regression",
        pairs=pairs,
        n_pairs=len(pairs),
        n_tier_worse=n_tier_worse,
        n_ttc_drop=n_ttc_drop,
        family_means=_family_means(pairs),
        passed=n_tier_worse == 0 and n_ttc_drop == 0,
    )


def build_comparison_b(
    candidate_samples: Sequence[Any],
    baseline_samples: Sequence[Any],
    *,
    candidate: str,
    baseline: str,
) -> RegressionReport:
    """Compare two models sample by sample. A comparison never gates, `passed` stays null."""
    base_by_id = {s.sample_id: s for s in baseline_samples}
    pairs: list[PairDelta] = []
    flips = 0
    for sample in sorted(candidate_samples, key=lambda s: s.sample_id):
        other = base_by_id.get(sample.sample_id)
        if other is None:
            continue
        worse = bool(sample.compliant) and not bool(other.compliant)
        refused_flip = bool(sample.refused) and not bool(other.refused)
        flips += 1 if worse else 0
        pairs.append(
            PairDelta(
                scenario_id=sample.sample_id,
                family=sample.task,
                ttc_baseline=_round(other.score),
                ttc_candidate=_round(sample.score),
                ttc_delta=_round(sample.score - other.score)
                if _finite(other.score) and _finite(sample.score)
                else None,
                tier_worse=worse,
                ttc_drop=refused_flip,
            )
        )
    return RegressionReport(
        candidate=candidate,
        baseline=baseline,
        kind="comparison",
        pairs=pairs,
        n_pairs=len(pairs),
        n_tier_worse=flips,
        n_ttc_drop=sum(1 for p in pairs if p.ttc_drop),
        family_means={},
        passed=None,
    )


__all__ = ["TTC_DROP_S", "tier_worse", "ttc_drop", "build_regression", "build_comparison_b"]
