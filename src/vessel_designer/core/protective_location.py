"""Protective location checks per IGF Code and IGC Code for Type C tanks."""

from dataclasses import dataclass
from enum import Enum


class VesselType(Enum):
    """Vessel/gas code classification controlling protective location rules."""
    IGF = "IGF"
    IGC_1G = "IGC_1G"
    IGC_2G = "IGC_2G"
    IGC_3G = "IGC_3G"
    # ADN tank vessel type G (inland waterways, UNECE). Added 2026-10-07 at Niall's request as
    # a selectable ruleset for river-only gas barges. Constant distances, NOT volume-stepped.
    ADN_G = "ADN_G"
    # IGC type 2G with d(Vc) applied EXACTLY as written (2.4.1.1, 2.4.2): linear bands, on
    # the INDIVIDUAL tank's gross volume, measured to the tank STEEL (insulation excluded).
    # Added 2026-10-07; "IGC_2G" keeps the engine's older conservative reading
    # so existing Ankobra numbers do not move until that change is decided.
    IGC_2G_EXACT = "IGC_2G_EXACT"


# ADN type G minimum distances (m), measured hull to tank (outer face, as the engine does).
# ONE place. Source check: docs/feasibility/tank-rules-research.md (ADN 2025, read 2026-10-06).
#  - Side: LNG (refrigerated) tanks may sit ONLY in double-hull holds (9.3.1.11.2(a)), and the
#    0.80 m is SIDE SHELL TO INNER HULL. ADN sets no inner-hull-to-tank figure; 0.45 m is taken by
#    analogy with IGC 3.5.3.5 (curved tank to plating, inspection passage). 0.80 + 0.45 = 1.25 m.
#  - Bottom: double bottom >= 0.60 m (9.3.1.11.2(a)); the tank sits on 0.50 m saddles above it,
#    so tank to keel = 0.60 + 0.50 = 1.10 m (the engine subtracts the saddle to get the double bottom).
ADN_G_DOUBLE_HULL_M = 0.80
ADN_G_INSPECTION_GAP_M = 0.45      # NOT an ADN value: IGC 3.5.3.5 analogy
ADN_G_SIDE_M = ADN_G_DOUBLE_HULL_M + ADN_G_INSPECTION_GAP_M
ADN_G_DOUBLE_BOTTOM_M = 0.60
ADN_G_SADDLE_M = 0.50
ADN_G_BOTTOM_M = ADN_G_DOUBLE_BOTTOM_M + ADN_G_SADDLE_M
# Per-tank capacity, 9.3.1.11.1(a): 380 m3 for hulls with L.B.H > 3,750 m3; up to 1,000 m3 (hard
# cap) only under the 9.3.4 alternative-construction risk comparison. Pressure tanks L/D <= 7
# (9.3.1.11.1(b)). Tank wider than 0.70 B triggers extra intact stability (9.3.1.14.2).
ADN_G_TANK_CAP_M3 = 380.0
ADN_G_TANK_CAP_9_3_4_M3 = 1000.0
ADN_G_MAX_L_OVER_D = 7.0
ADN_G_WIDE_TANK_FRACTION = 0.70


@dataclass
class ProtectiveLocationResult:
    """Result of protective location clearance checks."""
    vessel_type: str
    d_vc: float              # Volume-based minimum distance (m)
    total_tank_volume: float  # Vc used for d(Vc) lookup (m³)
    cs_required: float       # Required side clearance (m)
    cs_actual: float         # Actual side clearance (m)
    cs_ok: bool
    cb_required: float       # Required bottom clearance (m)
    cb_actual: float         # Actual bottom clearance (m)
    cb_ok: bool


def distance_d_vc(vc: float) -> float:
    """Volume-based minimum distance d(Vc) per IGC/IGF Code.

    Args:
        vc: Total tank volume in m³.

    Returns:
        Minimum distance in metres.
    """
    if vc <= 1000.0:
        return 0.8
    elif vc <= 5000.0:
        return 1.0
    else:
        return 2.0


def d_vc_exact(vc_individual_m3: float) -> float:
    """IGC 2.4.1.1 / IGF 5.3.3.4.2 d(Vc), exactly: Vc = gross volume of ONE tank (m3).

    Distance to the tank steel, excluding insulation (IGC 2.4.2).
    """
    v = float(vc_individual_m3)
    if v <= 1000.0:
        return 0.8
    if v < 5000.0:
        return 0.75 + v * 0.2 / 4000.0
    if v < 30000.0:
        return 0.8 + v / 25000.0
    return 2.0


def required_side_protection(vessel_type: VesselType, beam: float, d_vc: float) -> float:
    """Required side clearance Cs from tank to hull side.

    Args:
        vessel_type: Code classification.
        beam: Moulded beam (m).
        d_vc: Volume-based minimum distance (m).

    Returns:
        Required Cs in metres.
    """
    if vessel_type in (VesselType.IGF, VesselType.IGC_1G):
        return max(min(beam / 5.0, 11.5), d_vc)
    elif vessel_type == VesselType.IGC_2G:
        return d_vc
    elif vessel_type == VesselType.IGC_3G:
        return 0.8
    elif vessel_type == VesselType.ADN_G:
        return ADN_G_SIDE_M
    elif vessel_type == VesselType.IGC_2G_EXACT:
        return d_vc                     # caller passes d_vc_exact(per-tank Vc), steel datum
    else:
        raise ValueError(f"Unknown vessel type: {vessel_type}")


def required_bottom_protection(beam: float, d_vc: float, vessel_type: VesselType = None) -> float:
    """Required bottom clearance Cb from tank bottom to keel.

    Same formula for all vessel types.

    Args:
        beam: Moulded beam (m).
        d_vc: Volume-based minimum distance (m).

    Returns:
        Required Cb in metres.
    """
    if vessel_type == VesselType.ADN_G:
        return ADN_G_BOTTOM_M
    return max(min(beam / 15.0, 2.0), d_vc)


@dataclass
class RequiredClearances:
    """Required side and bottom clearances from protective location rules."""
    cs_required: float   # Required side clearance Cs (m)
    cb_required: float   # Required bottom clearance Cb (m)
    d_vc: float          # Volume-based minimum distance (m)


def compute_required_clearances(vessel_type_str: str, beam: float, d_vc: float) -> RequiredClearances:
    """Compute the required Cs and Cb for given vessel type, beam, and d(Vc).

    Args:
        vessel_type_str: One of "IGF", "IGC_1G", "IGC_2G", "IGC_3G".
        beam: Moulded beam (m).
        d_vc: Volume-based minimum distance d(Vc) in metres.

    Returns:
        RequiredClearances with cs_required, cb_required, and d_vc.
    """
    vessel_type = VesselType(vessel_type_str)
    cs_req = required_side_protection(vessel_type, beam, d_vc)
    cb_req = required_bottom_protection(beam, d_vc, vessel_type)
    return RequiredClearances(cs_required=cs_req, cb_required=cb_req, d_vc=d_vc)


def check_protective_location(
    vessel_type_str: str,
    beam: float,
    total_tank_volume: float,
    side_clearance: float,
    double_bottom_height: float,
    tank_support_height: float,
) -> ProtectiveLocationResult:
    """Run the full protective location check.

    Args:
        vessel_type_str: One of "IGF", "IGC_1G", "IGC_2G", "IGC_3G".
        beam: Moulded beam (m).
        total_tank_volume: Total interior volume of all tanks Vc (m³).
        side_clearance: Actual distance from tank to hull side (m).
        double_bottom_height: Double bottom height (m).
        tank_support_height: Tank saddle/support height above inner bottom (m).

    Returns:
        ProtectiveLocationResult with required vs actual clearances and pass/fail.
    """
    vessel_type = VesselType(vessel_type_str)
    d_vc = distance_d_vc(total_tank_volume)
    cs_req = required_side_protection(vessel_type, beam, d_vc)
    cb_req = required_bottom_protection(beam, d_vc, vessel_type)
    cb_actual = double_bottom_height + tank_support_height

    return ProtectiveLocationResult(
        vessel_type=vessel_type_str,
        d_vc=d_vc,
        total_tank_volume=total_tank_volume,
        cs_required=cs_req,
        cs_actual=side_clearance,
        cs_ok=side_clearance >= cs_req,
        cb_required=cb_req,
        cb_actual=cb_actual,
        cb_ok=cb_actual >= cb_req,
    )
