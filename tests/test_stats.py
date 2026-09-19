"""Clopper Pearson tests. Spec section 4.1, acceptance test AC-3."""

from __future__ import annotations

import pytest

from gate.stats import binom_cdf, cp_lower, cp_upper

LOWER_VECTORS = [
    (16, 16, 0.7941),
    (15, 16, 0.6977),
    (14, 16, 0.6165),
    (13, 16, 0.5435),
    (14, 14, 0.7684),
    (13, 14, 0.6613),
    (12, 14, 0.5719),
]
UPPER_VECTORS = [
    (0, 16, 0.2059),
    (1, 16, 0.3023),
    (0, 313, 0.0117),
    (3, 313, 0.0278),
    (10, 313, 0.0580),
    (10, 450, 0.0405),
    (23, 450, 0.0757),
]


@pytest.mark.parametrize(("k", "n", "expected"), LOWER_VECTORS)
def test_ac_3_cp_lower_vectors(k: int, n: int, expected: float) -> None:
    assert round(cp_lower(k, n), 4) == expected


@pytest.mark.parametrize(("k", "n", "expected"), UPPER_VECTORS)
def test_ac_3_cp_upper_vectors(k: int, n: int, expected: float) -> None:
    assert round(cp_upper(k, n), 4) == expected


def test_binom_cdf_is_exact() -> None:
    assert binom_cdf(10, 10, 0.3) == 1.0
    assert round(binom_cdf(0, 3, 0.5), 4) == 0.125
    assert round(binom_cdf(1, 2, 0.5), 4) == 0.75


def test_edge_cases() -> None:
    assert cp_lower(0, 16) == 0.0
    assert cp_upper(16, 16) == 1.0
    assert cp_lower(5, 10) < 0.5 < cp_upper(5, 10)
