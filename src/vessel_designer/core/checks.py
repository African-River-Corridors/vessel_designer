"""Shared validity-check primitive for the standardised module contract.

Every standardised module expresses its validity rules as a ``list[Check]`` on its
result, rather than as buried ``if``/raise logic, so the UI can render a red/green
list and tests can assert on them. See docs/feasibility/proposals/00-overview.md §1.

``severity`` lets a result distinguish a hard failure ("overloaded") from an advisory
("low freeboard") without abusing the free-text ``warnings`` list. ``result.ok`` is
conventionally ``all(c.ok for c in checks if c.severity == "error")``.

Pure Python — Pyodide-safe.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Check:
    """A single validity assertion about a design or calculation."""

    name: str
    ok: bool
    message: str
    severity: str = "error"   # "error" (gates result.ok) | "warning" (advisory)

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


def all_ok(checks) -> bool:
    """True if no error-severity check has failed (warnings don't gate)."""
    return all(c.ok for c in checks if getattr(c, "severity", "error") == "error")
