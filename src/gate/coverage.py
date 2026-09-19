"""Coverage bins and the not covered rows. Binding, see docs/ARCHITECTURE.md section 5.

Coverage answers one question. Which parts of the generation range did the
suite actually visit. The bin edges live in `configs/coverage_bins.yaml` and
are part of the contract. The not covered rows are fixed and never gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import yaml

from gate.schema import CoverageMatrix, CoverageRow, NotCoveredRow

DEFAULT_BINS_CONFIG = Path("configs/coverage_bins.yaml")


def load_bins_config(path: str | Path = DEFAULT_BINS_CONFIG) -> dict[str, Any]:
    """Read the bin configuration."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _round(value: float) -> float:
    """Round a float to four decimals."""
    return round(float(value), 4)


def bin_label(lo: float, hi: float) -> str:
    """Return the printable label of one bin."""
    return f"{_round(lo)}-{_round(hi)}"


def bin_index(value: float, edges: Sequence[float]) -> int | None:
    """Return the bin a value falls into, or None when it falls outside.

    The last bin is closed on the right, every other bin is closed on the left
    and open on the right.
    """
    n_bins = len(edges) - 1
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            if lo <= value <= hi:
                return i
        elif lo <= value < hi:
            return i
    return None


def row_status(n: int) -> str:
    """Return `empty` for zero, `sparse` for one, `ok` otherwise."""
    if n == 0:
        return "empty"
    if n == 1:
        return "sparse"
    return "ok"


def build_coverage(
    results: Sequence[Any],
    config: dict[str, Any] | None = None,
    *,
    track: str = "a",
) -> CoverageMatrix:
    """Build the Track A coverage matrix from the candidate results."""
    config = config or load_bins_config()
    families: dict[str, dict[str, list[float]]] = config.get("families", {})
    absolute = set(config.get("absolute_value_parameters", []))

    rows: list[CoverageRow] = []
    unbinned = 0
    for family in sorted(families):
        family_results = [r for r in results if getattr(r, "family", None) == family]
        for parameter in sorted(families[family]):
            edges = [float(e) for e in families[family][parameter]]
            buckets: list[list[str]] = [[] for _ in range(len(edges) - 1)]
            for result in family_results:
                value = (getattr(result, "parameters", {}) or {}).get(parameter)
                if value is None:
                    unbinned += 1
                    continue
                value = abs(float(value)) if parameter in absolute else float(value)
                index = bin_index(value, edges)
                if index is None:
                    unbinned += 1
                    continue
                buckets[index].append(getattr(result, "scenario_id", ""))
            for index, scenario_ids in enumerate(buckets):
                lo, hi = edges[index], edges[index + 1]
                rows.append(
                    CoverageRow(
                        family=family,
                        parameter=parameter,
                        bin_label=bin_label(lo, hi),
                        lo=_round(lo),
                        hi=_round(hi),
                        n=len(scenario_ids),
                        status=row_status(len(scenario_ids)),
                        scenario_ids=sorted(scenario_ids),
                    )
                )
    not_covered = [
        NotCoveredRow(hazard=item["hazard"], note_key=item["note_key"])
        for item in config.get("not_covered", [])
    ]
    return CoverageMatrix(
        track=track,
        rows=rows,
        unbinned=unbinned,
        not_covered=not_covered,
        passed=not any(row.status == "empty" for row in rows),
    )


def build_coverage_b(
    samples: Sequence[Any],
    hazards: Sequence[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> CoverageMatrix:
    """Build the Track B coverage matrix, one row per hazard, per spec 5.3."""
    config = config or {}
    rows: list[CoverageRow] = []
    mapped: set[str] = set()
    for hazard in sorted(hazards, key=lambda h: str(h.get("id", ""))):
        wanted = {str(c).lower() for c in hazard.get("maps_to", [])}
        mapped |= wanted
        ids = sorted(
            getattr(s, "sample_id", "")
            for s in samples
            if str(getattr(s, "category", "") or "").lower() in wanted
        )
        rows.append(
            CoverageRow(
                family="hazard",
                parameter=str(hazard.get("id", "")),
                bin_label=",".join(sorted(wanted)),
                lo=0.0,
                hi=0.0,
                n=len(ids),
                status=row_status(len(ids)),
                scenario_ids=ids,
            )
        )
    unmapped = sorted(
        {
            str(getattr(s, "category", "") or "")
            for s in samples
            if getattr(s, "category", None) and str(s.category).lower() not in mapped
        }
    )
    not_covered = [
        NotCoveredRow(hazard=item["hazard"], note_key=item["note_key"])
        for item in config.get("not_covered", [])
    ]
    return CoverageMatrix(
        track="b",
        rows=rows,
        unbinned=0,
        unmapped=unmapped,
        not_covered=not_covered,
        passed=not any(row.status == "empty" for row in rows),
    )


__all__ = [
    "DEFAULT_BINS_CONFIG",
    "load_bins_config",
    "bin_index",
    "bin_label",
    "row_status",
    "build_coverage",
    "build_coverage_b",
]
