"""Longitudinal separation between the gas cargo area and the rest of the vessel.

WHAT WAS MISSING. ``protective_location.py`` encodes the IGC/IGF PROTECTIVE LOCATION rules,
which are TRANSVERSE (Cs, tank to shell) and VERTICAL (Cb, tank to bottom). Nothing in the
model separated the cargo tanks from the accommodation, the wheelhouse or the machinery
ALONG THE LENGTH: the aft tank head sat directly against the stern block. That is the rule
this module supplies, and it costs cargo length.

THE RULES, and which one governs for us (checked 2026-09-18 against the classification
rules for inland-waterways ships carrying dangerous liquids in bulk, Part 4 Ch. 4 Sec. 3,
July 2022 — the inland implementation of ADN Part 9, and consistent with IGC Code 3.1):

  * 3.3.9   Accommodation spaces and the wheelhouse shall be located OUTSIDE the cargo
            area, forward of the fore or abaft the aft vertical plane bounding the part of
            the cargo area below deck.
  * 3.5.3   (type G — liquefied gas) Hold spaces shall be separated from accommodation and
            service spaces outside the cargo area below deck by bulkheads with A-60 fire
            protection insulation. NOTE: for type G this is an insulated BULKHEAD rule, not
            a dimensioned cofferdam. The 0,60 m cofferdam is the type C / type N rule
            (3.6.13, 3.7.4) and IGC 3.1.2 offers the same either/or.
  * 3.3.7   Engine-room entrances not less than 2,00 m from the cargo area.
  * 3.3.11  Entrances and openable windows of superstructures and accommodation spaces
            not less than 2,00 m from the cargo area.
  * 3.5.2   (type G) Internal distance side plating to longitudinal bulkhead not less than
            0,80 m; double bottom not less than 0,60 m. A FLOOR under the IGC d(Vc) values.
  * 3.5.3 / 3.6.3  Space between the tanks and the end bulkheads not less than 0,50 m,
            reducible to 0,20 m where the tank is a pressure tank.

WHAT GOVERNS AFT. The A-60 bulkhead carries no width, so on its own it would take no
length. The binding number is the 2,00 m setback of any openable entrance or window
(3.3.11) and of the engine-room entrance (3.3.7) from the cargo area. A deckhouse whose
front bulkhead is flush with the cargo area cannot have a door or a window in it. So the
DESIGN RULE ADOPTED HERE is a 2,00 m aft separation, built as a 0,60 m cofferdam plus
1,40 m of service space, which satisfies the bulkhead rule, the cofferdam convention and
the opening setback at once. Override it if a designer places the openings elsewhere.

OPEN: the clause numbers above are the classification-society implementation. Confirm them
against the ADN text itself before any of this leaves the project — RFI Q-ANK gas-sep-1.

Pure functions + typed dataclasses; no I/O. Runs in Pyodide.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .checks import Check, all_ok

# --- Rule constants, each with its clause. Do not retype these anywhere else. ---
COFFERDAM_MIN_M = 0.60          # 3.6.13 / 3.7.4 (type C/N convention; IGC 3.1.2 either/or)
OPENING_SETBACK_M = 2.00        # 3.3.7 + 3.3.11 — entrances/windows from the cargo area
END_BULKHEAD_SPACE_M = 0.50     # 3.5.3 / 3.6.3
END_BULKHEAD_SPACE_PRESSURE_M = 0.20    # same clause, pressure tanks
SIDE_MIN_TYPE_G_M = 0.80        # 3.5.2 — floor under the IGC d(Vc) side clearance
DOUBLE_BOTTOM_MIN_TYPE_G_M = 0.60       # 3.5.2


@dataclass
class GasSeparationInputs:
    """Inputs for the longitudinal cargo-area separation."""

    cofferdam_m: float = COFFERDAM_MIN_M
    opening_setback_m: float = OPENING_SETBACK_M
    # Type-C tanks are pressure vessels, so the clause permits 0,20 m forward. The default
    # here is the UNREDUCED 0,50 m: the saving is immaterial and the reduction needs a
    # designer's call, not a default.
    fwd_end_bulkhead_m: float = END_BULKHEAD_SPACE_M
    is_pressure_tank: bool = True
    # As-designed values, for the checks
    side_clearance_m: float = 0.0
    double_bottom_m: float = 0.0

    def __post_init__(self):
        if self.cofferdam_m < 0 or self.opening_setback_m < 0 or self.fwd_end_bulkhead_m < 0:
            raise ValueError("separations must be non-negative")


@dataclass
class GasSeparationResult:
    """The length the gas code takes off the cargo area at each end."""

    aft_separation_m: float         # cargo area aft boundary -> front of the stern block
    fwd_separation_m: float         # cargo area fwd boundary -> forward end bulkhead
    cofferdam_m: float
    service_space_m: float          # the remainder of the aft separation, aft of the cofferdam
    total_length_taken_m: float

    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def compute(inp: GasSeparationInputs) -> GasSeparationResult:
    """Resolve the aft and forward separations, with the rules as checks."""
    aft = max(inp.cofferdam_m, inp.opening_setback_m)
    fwd = inp.fwd_end_bulkhead_m
    service = max(0.0, aft - inp.cofferdam_m)

    floor = (END_BULKHEAD_SPACE_PRESSURE_M if inp.is_pressure_tank
             else END_BULKHEAD_SPACE_M)

    checks = [
        Check("cofferdam_min_width", inp.cofferdam_m >= COFFERDAM_MIN_M - 1e-9,
              f"cofferdam {inp.cofferdam_m:.2f} m >= {COFFERDAM_MIN_M:.2f} m (cl. 3.6.13)"),
        Check("opening_setback", aft >= OPENING_SETBACK_M - 1e-9,
              f"aft separation {aft:.2f} m >= {OPENING_SETBACK_M:.2f} m from the cargo area "
              f"to any entrance or openable window (cl. 3.3.7 / 3.3.11)"),
        Check("fwd_end_bulkhead_space", fwd >= floor - 1e-9,
              f"forward end-bulkhead space {fwd:.2f} m >= {floor:.2f} m "
              f"({'pressure tank' if inp.is_pressure_tank else 'standard'}, cl. 3.5.3 / 3.6.3)"),
    ]
    if inp.side_clearance_m > 0:
        checks.append(Check(
            "side_clearance_type_g_floor", inp.side_clearance_m >= SIDE_MIN_TYPE_G_M - 1e-9,
            f"side clearance {inp.side_clearance_m:.2f} m >= {SIDE_MIN_TYPE_G_M:.2f} m "
            f"inland type-G floor (cl. 3.5.2); IGC d(Vc) may require more"))
    if inp.double_bottom_m > 0:
        checks.append(Check(
            "double_bottom_type_g_floor",
            inp.double_bottom_m >= DOUBLE_BOTTOM_MIN_TYPE_G_M - 1e-9,
            f"double bottom {inp.double_bottom_m:.2f} m >= "
            f"{DOUBLE_BOTTOM_MIN_TYPE_G_M:.2f} m inland type-G floor (cl. 3.5.2)"))

    warnings = [
        "Separation clauses are cited from the classification rules for inland-waterways "
        "ships (Pt 4 Ch 4 Sec 3, Jul 2022). Confirm against the ADN text before release."
    ]
    return GasSeparationResult(
        aft_separation_m=aft, fwd_separation_m=fwd,
        cofferdam_m=inp.cofferdam_m, service_space_m=service,
        total_length_taken_m=aft + fwd,
        checks=checks, warnings=warnings,
    )
