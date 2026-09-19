"""Gate file loading, hashing, waivers and deviations. Spec sections 3.4 and 3.7.

The gate file is the pre registered contract. Its hash covers the whole file
bytes, so any edit is visible. Waivers and deviations live outside the hashed
file, one YAML each per suite.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from gate.schema import SCHEMA_VERSION, Deviation, GateFile, GateSpec, Waiver

DEFAULT_TRACK_A_GATES = Path("gates/track_a.yaml")
DEFAULT_TRACK_B_GATES = Path("gates/track_b.yaml")
OWNER_COPY_MARKER = "[[OWNER_COPY"


def sha256_file(path: str | Path) -> str:
    """Return the SHA 256 of the whole file in lowercase hex."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed_from_hash(sha256: str) -> int:
    """Return the Track A seed, the first eight hex characters as an integer."""
    return int(sha256[:8], 16)


def load_gate_file(path: str | Path) -> GateFile:
    """Read a gate file and validate it against the schema.

    Raises ValueError when the schema version does not match the one this
    build understands.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    gate_file = GateFile.model_validate(raw)
    if gate_file.schema_version != SCHEMA_VERSION:
        raise ValueError(f"gate file {path} has schema_version {gate_file.schema_version}, expected {SCHEMA_VERSION}")
    return gate_file


def has_owner_copy(path: str | Path) -> bool:
    """Return True when the gate file still carries an owner copy placeholder."""
    return OWNER_COPY_MARKER in Path(path).read_text(encoding="utf-8")


def gate_by_id(gate_file: GateFile, gate_id: str) -> GateSpec | None:
    """Return the gate with this id, or None."""
    for gate in gate_file.gates:
        if gate.id == gate_id:
            return gate
    return None


def load_waivers(path: str | Path) -> list[Waiver]:
    """Read `waivers.yaml`. A missing file means no waivers."""
    path = Path(path)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(raw, dict):
        raw = raw.get("waivers", [])
    return [Waiver.model_validate(item) for item in raw]


def load_deviations(path: str | Path) -> list[Deviation]:
    """Read `deviations.yaml`. A missing file means no deviations."""
    path = Path(path)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(raw, dict):
        raw = raw.get("deviations", [])
    return [Deviation.model_validate(item) for item in raw]


def rationale_strings(gate_file: GateFile) -> dict[str, str]:
    """Return gate rationales and sources for the strings merge.

    Rationales land under `rationale.<gate id>`, sources under `gate.source.<gate id>`,
    so the dashboard cites the gate file rather than a hand kept copy.
    """
    strings = {f"rationale.{gate.id}": gate.rationale for gate in gate_file.gates}
    strings.update({f"gate.source.{gate.id}": gate.source for gate in gate_file.gates})
    return strings


__all__ = [
    "DEFAULT_TRACK_A_GATES",
    "DEFAULT_TRACK_B_GATES",
    "OWNER_COPY_MARKER",
    "sha256_file",
    "seed_from_hash",
    "load_gate_file",
    "has_owner_copy",
    "gate_by_id",
    "load_waivers",
    "load_deviations",
    "rationale_strings",
]
