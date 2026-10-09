"""Barge design-space sweep: gas cargo vs beam, for a family of barge lengths.

Pre-computes volume-bound gas cargo (Type-C tanks) across a grid of barge length
x beam, so the report can draw the cargo-against-beam curves (one line per LOA)
without any live calculation.

Design rule for the tank count (the one free choice as length grows):
  n_tanks_long = max(1, ceil(available_length / max_tank_length))
where available_length = (1 - bow_pct - stern_pct) * barge_length. The count
depends on LENGTH ONLY (not beam), so every fixed-LOA curve is smooth — you only
step up a tank when the hull gets long enough to need one. max_tank_length is a
fabrication/transport/support limit (ESTIMATE, 28 m; the published 60 m barge
carries 2 tanks at ~21.5 m each, comfortably under). The base point
(60 m x 12 m beam, 1.0 m standard clearance) reproduces the published ~1,128 t.

Cargo is sized on the BARGE length (the tank-bearing hull) per the report's
Ch.5 capacity rule; total ATB LOA = barge length + tug (16 m for the E-Pusher).

Pure Python (Pyodide-safe): wraps barge_capacity.compute, no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .barge_capacity import BargeCapacityInputs, compute as _capacity

MAX_TANK_LENGTH_M = 28.0       # overall Type-C tank length cap — ESTIMATE
SIDE_CLEARANCE_M = 1.0         # standard IGC-2G protective-location spacing per side
BOW_NON_TANK_PCT = 0.10        # mirror models.py defaults
STERN_NON_TANK_PCT = 0.15
TUG_LOA_M = 16.0               # Kotug E-Pusher pattern — for the total-LOA note


def n_tanks_for_length(barge_length_m: float,
                       max_tank_length_m: float = MAX_TANK_LENGTH_M) -> int:
    """Tanks in a line for a given barge length (length-only, so curves stay smooth)."""
    available = (1.0 - BOW_NON_TANK_PCT - STERN_NON_TANK_PCT) * barge_length_m
    return max(1, math.ceil(available / max_tank_length_m))


@dataclass
class GridCell:
    barge_length_m: float
    beam_m: float
    n_tanks_long: int
    feasible: bool
    cargo_t: Optional[float] = None            # volume-bound (1.0 m standard side clearance)
    tank_outer_diameter_m: Optional[float] = None
    tank_length_m: Optional[float] = None
    slenderness: Optional[float] = None         # overall tank length / OD
    full_load_draft_m: Optional[float] = None
    air_draft_m: Optional[float] = None
    reason: str = ""                            # why infeasible, if so


@dataclass
class DesignGrid:
    barge_lengths_m: List[float]
    beams_m: List[float]
    depth_m: float
    cargo_type: str
    clearance_basis: str
    max_tank_length_m: float
    cells: List[GridCell] = field(default_factory=list)

    def curve(self, barge_length_m: float) -> List[GridCell]:
        """Feasible cells for one barge length, ordered by beam (one plotted line)."""
        return [c for c in self.cells
                if c.barge_length_m == barge_length_m and c.feasible]


def _cell(barge_length_m: float, beam_m: float, depth_m: float,
          cargo_type: str) -> GridCell:
    n = n_tanks_for_length(barge_length_m)
    try:
        r = _capacity(BargeCapacityInputs(
            loa=barge_length_m, beam=beam_m, depth=depth_m, cargo_type=cargo_type,
            n_tanks_long=n, side_clearance_override_m=SIDE_CLEARANCE_M))
    except Exception as exc:
        return GridCell(barge_length_m, beam_m, n, feasible=False,
                        reason=str(exc)[:80])
    od = r.tank_outer_diameter_m or 0.0
    tank_len = r.cargo_volume_m3 and _tank_overall_length(barge_length_m, n)
    # `barge_capacity` stopped RAISING on impossible geometry on 2026-09-18 and started
    # returning a failed `feasible_geometry` check with zero cargo, so a sweep can finish.
    # Read that, or every impossible cell reports feasible with 0 t.
    if not r.ok or r.cargo_capacity_t <= 0:
        why = next((c.message for c in r.checks if not c.ok), "no cargo volume")
        return GridCell(barge_length_m, beam_m, n, feasible=False, reason=why[:80])
    return GridCell(
        barge_length_m=barge_length_m, beam_m=beam_m, n_tanks_long=n, feasible=True,
        cargo_t=r.cargo_capacity_t,
        tank_outer_diameter_m=od, tank_length_m=tank_len,
        slenderness=(tank_len / od if od else None),
        full_load_draft_m=r.full_load_draft_m, air_draft_m=r.air_draft_m,
    )


def _tank_overall_length(barge_length_m: float, n: int) -> float:
    available = (1.0 - BOW_NON_TANK_PCT - STERN_NON_TANK_PCT) * barge_length_m
    return (available - (n - 1) * 2.0) / n     # 2.0 m longitudinal gap (models default)


def sweep(barge_lengths_m: List[float], beams_m: List[float],
          depth_m: float = 6.0, cargo_type: str = "LPG_propane") -> DesignGrid:
    grid = DesignGrid(
        barge_lengths_m=list(barge_lengths_m), beams_m=list(beams_m),
        depth_m=depth_m, cargo_type=cargo_type,
        clearance_basis="1.0 m standard side clearance per side (IGC-2G protective location)",
        max_tank_length_m=MAX_TANK_LENGTH_M,
    )
    for loa in barge_lengths_m:
        for beam in beams_m:
            grid.cells.append(_cell(float(loa), float(beam), depth_m, cargo_type))
    return grid
