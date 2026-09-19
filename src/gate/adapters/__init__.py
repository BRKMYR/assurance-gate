"""Adapters that turn foreign evaluation artefacts into the contracts of schema.py.

Every adapter is a pure reader. It never writes into the source tree, it drops
private fields such as `trajectory_log`, and it returns only the public records
defined in docs/ARCHITECTURE.md section 3.
"""

from __future__ import annotations

__all__ = ["avsb", "inspect_"]
