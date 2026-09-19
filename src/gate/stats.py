"""Exact binomial statistics without scipy. Binding, see docs/ARCHITECTURE.md section 4.1.

Only two things are needed by the engine: the exact binomial cumulative
distribution function and the two Clopper Pearson bounds. Both are computed
with `math.comb` and a fixed bisection, so the numbers are identical on every
machine and on every run.
"""

from __future__ import annotations

from math import comb

ALPHA = 0.05
ITERATIONS = 200


def binom_pmf(k: int, n: int, p: float) -> float:
    """Return the exact binomial probability mass at k successes out of n."""
    if k < 0 or k > n:
        return 0.0
    return comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def binom_cdf(k: int, n: int, p: float) -> float:
    """Return P(X <= k) for X binomial with n trials and success probability p."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(binom_pmf(i, n, p) for i in range(0, k + 1))


def binom_sf_ge(k: int, n: int, p: float) -> float:
    """Return P(X >= k) for X binomial with n trials and success probability p."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return 1.0 - binom_cdf(k - 1, n, p)


def _bisect(target: float, fn, decreasing: bool) -> float:
    """Return the p in [0, 1] where fn(p) equals target, by fixed bisection.

    `decreasing` says whether fn falls as p rises. The loop count is fixed so
    that the result never depends on a tolerance.
    """
    lo, hi = 0.0, 1.0
    for _ in range(ITERATIONS):
        mid = (lo + hi) / 2.0
        value = fn(mid)
        if (value > target) == decreasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def cp_lower(k: int, n: int, alpha: float = ALPHA) -> float:
    """Return the Clopper Pearson lower bound for k successes out of n."""
    if n <= 0:
        return 0.0
    if k <= 0:
        return 0.0
    if k > n:
        raise ValueError("k cannot exceed n")
    return _bisect(alpha / 2.0, lambda p: binom_sf_ge(k, n, p), decreasing=False)


def cp_upper(k: int, n: int, alpha: float = ALPHA) -> float:
    """Return the Clopper Pearson upper bound for k successes out of n."""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    if k < 0:
        raise ValueError("k cannot be negative")
    return _bisect(alpha / 2.0, lambda p: binom_cdf(k, n, p), decreasing=True)


__all__ = ["ALPHA", "binom_pmf", "binom_cdf", "binom_sf_ge", "cp_lower", "cp_upper"]
