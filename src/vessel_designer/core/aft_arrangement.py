"""Aft arrangement — the self-propelled vessel's stern block, derived from its equipment.

WHY THIS MODULE EXISTS. The stern non-cargo length was a FRACTION of LOA
(``stern_void_fraction = 0.15``), typed once and then relied on by the capacity model, the
drawings and the material count. A fraction is not a design: it does not know whether three
thrusters fit across the beam, whether a 40 ft accommodation unit fits between the thruster
room and the cargo-area bulkhead, or how high the wheelhouse has to be to see over the
cargo. This module builds the stern block from the equipment that has to go in it and
returns its LENGTH, so the capacity model deducts a length it can justify.

The same block serves the gas tanker and the dry-bulk hopper — Niall, 2026-09-18: one
40 ft battery unit, one 40 ft accommodation unit, three electric thrusters, and a
wheelhouse that lifts clear of the cargo.

ARRANGEMENT, stern -> bow:
    [ thruster / steering compartment ]
    [ 40 ft units, SIDE BY SIDE across the beam -- battery and accommodation ]
    [ wheelhouse, on deck, on a lifting column ]

The MIX of units differs by cargo (Niall, 2026-09-18): the dry-bulk vessel carries a second
BATTERY (it is the heavier hull and the longer leg), the gas vessel a second ACCOMMODATION
unit (a gas vessel is manned differently). Three units ABREAST either way, which costs beam
and not length -- 10.91 m of it.

A NARROW hull cannot do that: three 40 ft units abreast need 10.91 m, and the 8 m and 10 m
beam alternatives have neither. So the units overflow into a SECOND ROW fore-and-aft, which
lengthens the block and costs cargo. That is the real trade a narrow vessel makes, and it
is the reason this is modelled rather than gated: gating would have deleted the 8 m and
10 m columns of the design grid on a fact about ISO containers.

The wheelhouse is FORWARD of the containers and stows at DECK level, not on top of them.
That is the whole point of a lifting wheelhouse: stowed it is the lowest it can be, so it
does not drive the transit air draft, and raised its eye clears the cargo. Stowing it on
the container roof would add the container height to every bridge clearance.

The gas-code separation between this block and the cargo area is NOT here — it is a
cargo-code rule and lives in ``gas_separation.py``. Keeping them apart is deliberate: the
equipment does not change when the cargo does, and the separation does.

Pure functions + typed dataclasses; no I/O. Runs in Pyodide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .checks import Check, all_ok

# --- ISO 40 ft container envelope (ISO 668 series 1, 1AAA high-cube) ---
ISO40_LENGTH_M = 12.192
ISO40_WIDTH_M = 2.438
ISO40_HEIGHT_HC_M = 2.896
ISO40_HEIGHT_STD_M = 2.591


@dataclass
class AftArrangementInputs:
    """What has to fit in the stern block, and how much room each item needs."""

    beam: float                              # moulded beam (m)
    depth: float                             # moulded depth = main deck above keel (m)

    # --- Propulsion (electric azimuth/tunnel units) ---
    # REQUESTED number of units (Niall, 2026-09-18: three). It is a MAXIMUM, not a
    # promise: `compute` fits as many as the beam takes and reports the shortfall, because
    # a thruster size is set by power, not by beam, and three 2.6 m units do not go across
    # an 8 m hull at any clearance. Gating on it would delete half the design grid on the
    # strength of one estimate.
    n_thrusters: int = 3
    thruster_envelope_m: float = 2.60        # transverse envelope of one unit (m)
    thruster_clear_m: float = 0.60           # clear structure between units and to the shell
    thruster_room_length_m: float = 3.50     # steering flat / thruster compartment (m)

    # --- Containerised battery and accommodation (40 ft ISO, side by side) ---
    # Defaults are the GAS vessel's mix. `barge_capacity` swaps them for dry bulk.
    n_battery_units: int = 1
    n_accom_units: int = 2
    container_length_m: float = ISO40_LENGTH_M
    container_width_m: float = ISO40_WIDTH_M
    container_height_m: float = ISO40_HEIGHT_HC_M
    container_side_gap_m: float = 0.90       # walkway between and outboard of the units
    container_gap_m: float = 0.80             # clear between rows, fore and aft (m)
    container_foundation_m: float = 0.30     # seatings/stool under a deck-mounted unit (m)

    # --- Wheelhouse (lifting) ---
    wheelhouse_length_m: float = 3.60
    wheelhouse_width_m: float = 6.40         # wider (Niall, 2026-09-18)
    wheelhouse_height_m: float = 3.40        # floor to roof (m) -- taller
    wheelhouse_gap_m: float = 0.30           # clear between the containers and the cab
    wheelhouse_eye_above_floor_m: float = 1.50
    # Height above keel the helmsman's eye must clear when raised. None = no cargo to see
    # over, so the wheelhouse stays in its lowered (transit) position.
    sightline_obstruction_m: Optional[float] = None
    sightline_margin_m: float = 0.50         # eye above the obstruction (m)
    wheelhouse_max_lift_m: float = 6.00      # stroke of the lifting column (m)

    def __post_init__(self):
        if self.beam <= 0 or self.depth <= 0:
            raise ValueError("beam and depth must be positive")
        if self.n_thrusters < 1:
            raise ValueError("n_thrusters must be >= 1")


@dataclass
class AftArrangementResult:
    """The stern block, dimensioned. All x are metres FORWARD of the stern (x = 0)."""

    length_m: float                          # total block length the hull must give it

    # Longitudinal zones, (label, x_aft, x_fwd)
    zones: list = field(default_factory=list)

    # Transverse thruster centres, metres from the centreline (+ = port)
    thruster_offsets_m: list = field(default_factory=list)
    thruster_room_length_m: float = 0.0

    # Container block
    container_x0_m: float = 0.0
    container_x1_m: float = 0.0
    container_total_width_m: float = 0.0
    container_top_above_keel_m: float = 0.0
    # One label per unit, port to starboard, so the plan draws what the model counted
    # rather than assuming a fixed pair.
    container_labels: list = field(default_factory=list)
    container_unit_width_m: float = 0.0
    container_side_gap_m: float = 0.0
    container_rows: int = 1
    container_per_row: int = 0
    container_row_length_m: float = 0.0
    container_row_gap_m: float = 0.0

    # Wheelhouse
    wheelhouse_x0_m: float = 0.0
    wheelhouse_x1_m: float = 0.0
    wheelhouse_floor_lowered_m: float = 0.0  # above keel
    wheelhouse_top_lowered_m: float = 0.0    # above keel — the TRANSIT air-draft top
    wheelhouse_floor_raised_m: float = 0.0
    wheelhouse_top_raised_m: float = 0.0     # above keel — the NAVIGATING top
    wheelhouse_lift_m: float = 0.0           # stroke actually used
    wheelhouse_width_m: float = 0.0
    wheelhouse_height_m: float = 0.0

    # The tallest fixed point of the block in the transit (lowered) condition
    block_top_lowered_m: float = 0.0

    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def compute(inp: AftArrangementInputs) -> AftArrangementResult:
    """Build the stern block from its equipment. Pure."""
    n_units = inp.n_battery_units + inp.n_accom_units

    # --- How many units go ABREAST, and how many rows that needs ---------------------
    # Abreast is the arrangement (Niall). A hull too narrow for the full row overflows
    # into a second row fore-and-aft, which lengthens the block rather than failing.
    per_row_fit = int((inp.beam - inp.container_side_gap_m)
                      // (inp.container_width_m + inp.container_side_gap_m))
    n_per_row = max(1, min(n_units, per_row_fit))
    n_rows = -(-n_units // n_per_row)          # ceil

    # --- Longitudinal build-up, stern (x=0) forward ---
    x = 0.0
    zones = []
    thr_x0, thr_x1 = x, x + inp.thruster_room_length_m
    zones.append(("THRUSTER ROOM", thr_x0, thr_x1))
    x = thr_x1

    cont_x0 = x + inp.container_foundation_m
    cont_x1 = cont_x0 + n_rows * inp.container_length_m + (n_rows - 1) * inp.container_gap_m
    zones.append((f"{int(round(inp.container_length_m / 0.3048))} FT UNITS "
                  f"({n_per_row} ABREAST x {n_rows})", cont_x0, cont_x1))

    wh_x0 = cont_x1 + inp.wheelhouse_gap_m
    wh_x1 = wh_x0 + inp.wheelhouse_length_m
    zones.append(("WHEELHOUSE (LIFTING)", wh_x0, wh_x1))
    length = wh_x1

    # --- Transverse: thrusters equally spaced, containers side by side ---
    pitch = inp.thruster_envelope_m + inp.thruster_clear_m
    usable = inp.beam - 2.0 * inp.thruster_clear_m
    n_fit = int((usable + inp.thruster_clear_m) // pitch) if pitch > 0 else 0
    n_thr = max(1, min(inp.n_thrusters, n_fit))
    span = (n_thr - 1) * pitch
    offsets = [(-span / 2.0 + i * pitch) for i in range(n_thr)]
    thruster_beam_needed = span + inp.thruster_envelope_m + 2.0 * inp.thruster_clear_m
    requested_beam_needed = ((inp.n_thrusters - 1) * pitch + inp.thruster_envelope_m
                             + 2.0 * inp.thruster_clear_m)

    cont_w = (n_per_row * inp.container_width_m
              + (n_per_row + 1) * inp.container_side_gap_m)
    labels = (["BATTERY 40 FT"] * inp.n_battery_units
              + ["ACCOM 40 FT"] * inp.n_accom_units)

    # --- Vertical: containers on deck; the wheelhouse STOWS at deck level ---
    deck = inp.depth
    cont_top = deck + inp.container_foundation_m + inp.container_height_m

    wh_floor_lo = deck
    wh_top_lo = wh_floor_lo + inp.wheelhouse_height_m

    lift = 0.0
    if inp.sightline_obstruction_m is not None:
        # The eye must sit `margin` above the tallest thing forward of it.
        eye_lo = wh_floor_lo + inp.wheelhouse_eye_above_floor_m
        needed = inp.sightline_obstruction_m + inp.sightline_margin_m
        lift = max(0.0, needed - eye_lo)
    lift_used = min(lift, inp.wheelhouse_max_lift_m)
    wh_floor_hi = wh_floor_lo + lift_used
    wh_top_hi = wh_floor_hi + inp.wheelhouse_height_m

    checks = [
        Check("thrusters_fit_beam", thruster_beam_needed <= inp.beam,
              f"{n_thr} x {inp.thruster_envelope_m:.2f} m thrusters need "
              f"{thruster_beam_needed:.2f} m across a {inp.beam:.2f} m beam"),
        Check("requested_thruster_count_fits", n_thr >= inp.n_thrusters,
              f"{n_thr} of {inp.n_thrusters} requested thrusters fit; "
              f"{inp.n_thrusters} would need {requested_beam_needed:.2f} m of "
              f"{inp.beam:.2f} m beam", severity="warning"),
        Check("containers_fit_beam", cont_w <= inp.beam,
              f"{n_per_row} x 40 ft units abreast need {cont_w:.2f} m across a "
              f"{inp.beam:.2f} m beam"),
        Check("units_fit_in_one_row", n_rows == 1,
              f"{n_units} units in {n_rows} row(s) of {n_per_row}; a second row adds "
              f"{inp.container_length_m + inp.container_gap_m:.2f} m to the stern block "
              f"and comes straight off the cargo zone", severity="warning"),
        Check("wheelhouse_fits_beam", inp.wheelhouse_width_m <= inp.beam,
              f"wheelhouse {inp.wheelhouse_width_m:.2f} m wide on a "
              f"{inp.beam:.2f} m beam"),
    ]
    warnings = []
    if inp.sightline_obstruction_m is not None:
        cleared = (wh_floor_hi + inp.wheelhouse_eye_above_floor_m) >= (
            inp.sightline_obstruction_m + inp.sightline_margin_m - 1e-9)
        # WARNING, not a gate. The stroke of the lifting column is an assumption; a cargo
        # top the wheelhouse cannot see over is a real design problem, but it is solved by
        # a taller column or a lower tank, not by declaring the vessel impossible.
        checks.append(Check(
            "wheelhouse_sees_over_cargo", cleared, severity="warning", message=
            f"raised eye {wh_floor_hi + inp.wheelhouse_eye_above_floor_m:.2f} m >= "
            f"obstruction {inp.sightline_obstruction_m:.2f} m + "
            f"{inp.sightline_margin_m:.2f} m margin "
            f"(lift used {lift_used:.2f} m of {inp.wheelhouse_max_lift_m:.2f} m)"))
        if lift > inp.wheelhouse_max_lift_m + 1e-9:
            warnings.append(
                f"Sightline needs {lift:.2f} m of lift; the column gives "
                f"{inp.wheelhouse_max_lift_m:.2f} m. Raise the column or lower the cargo top.")

    return AftArrangementResult(
        length_m=length,
        zones=zones,
        thruster_offsets_m=offsets,
        thruster_room_length_m=inp.thruster_room_length_m,
        container_x0_m=cont_x0, container_x1_m=cont_x1,
        container_total_width_m=cont_w,
        container_top_above_keel_m=cont_top,
        container_labels=labels,
        container_unit_width_m=inp.container_width_m,
        container_side_gap_m=inp.container_side_gap_m,
        container_rows=n_rows,
        container_per_row=n_per_row,
        container_row_length_m=inp.container_length_m,
        container_row_gap_m=inp.container_gap_m,
        wheelhouse_x0_m=wh_x0, wheelhouse_x1_m=wh_x1,
        wheelhouse_floor_lowered_m=wh_floor_lo, wheelhouse_top_lowered_m=wh_top_lo,
        wheelhouse_floor_raised_m=wh_floor_hi, wheelhouse_top_raised_m=wh_top_hi,
        wheelhouse_lift_m=lift_used,
        wheelhouse_width_m=inp.wheelhouse_width_m,
        wheelhouse_height_m=inp.wheelhouse_height_m,
        block_top_lowered_m=max(cont_top, wh_top_lo),
        checks=checks, warnings=warnings,
    )
