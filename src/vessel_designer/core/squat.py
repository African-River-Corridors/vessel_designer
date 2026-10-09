"""Squat — how much deeper a moving vessel sits than a stationary one.

WHY THIS MODULE EXISTS. `resistance.py` computed a service speed from resistance alone and
returned 9.2 knots for the laden CN II motor in the 4.80 m Ankobra channel. At that speed the
vessel squats about 1.7 m into an under-keel clearance of 0.40 m. It would be aground long
before it was underpowered. Squat, not power, is what limits speed in a shallow canalised
river, and the engine had no model of it at all.

The effect is strongly non-linear — roughly V^2 — so it does not merely trim the answer, it
halves it. Between a 4.80 m channel (UKC 0.40 m) and a 5.28 m one (UKC 0.88 m) the laden
service speed goes from under 4 knots to about 6.5.

TWO METHODS, BOTH EMPIRICAL, AND THE DIFFERENCE IS REPORTED
-----------------------------------------------------------
There is no closed-form squat. Both of these are fits to model and full-scale data, and they
disagree by tens of percent, which is itself worth seeing on a sheet.

**Barrass II** (Barrass, 1979 and later; the form quoted in his *Ship Squat* work)::

    S_max = C_b * S^0.81 * V_k^2.08 / 20        [m]

with ``S`` the blockage ratio (midship area / channel section area) and ``V_k`` the speed
THROUGH WATER in knots. Barrass gives this for confined and restricted channels and it is the
one usually reached for in inland work. It is dimensionally inhomogeneous — the constants
carry the units — which is normal for this class of formula and a reason to treat it as an
estimate, not a calculation.

**ICORELS / PIANC** for the bow of a slender ship::

    S_max = 2.4 * (Vol / L_pp^2) * F_nh^2 / sqrt(1 - F_nh^2)

with ``F_nh = V / sqrt(g*h)`` the depth Froude number. This is the form PIANC's channel-design
guidance uses. It blows up as ``F_nh -> 1`` — correctly, because that is the critical speed —
so it is only meaningful below about 0.7 and the result says so.

WHAT THIS DOES NOT DO
---------------------
* No trim: it returns MAXIMUM squat, not bow-down or stern-down separately. For a full-bodied
  barge (C_b 0.85) maximum squat is at the bow; for a fine hull it can be at the stern.
* No passing-vessel or bank-suction effect, both of which add squat in a narrow channel.
* No wave-induced or wind-induced motion. In a river that is right; at sea it is not, and this
  module should not be used for the sea leg.
* No dynamic heel from turning, which in a bend adds draught on the outboard bilge.

Pure functions, math only — Pyodide-safe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .checks import Check, all_ok

GRAVITY = 9.80665

#: Under-keel clearance we insist remains BELOW the squatted keel. Not a standard's number:
#: a working margin for survey error, siltation between dredging campaigns, and the fact that
#: squat itself is an estimate. PIANC's own net-UKC allowances for a river are of this order.
DEFAULT_SAFETY_MARGIN_M = 0.15

#: Above this depth Froude number the ICORELS form is no longer meaningful and the flow is
#: approaching critical. Reported as a failed check rather than silently extrapolated.
FNH_VALID_MAX = 0.70


@dataclass(frozen=True)
class SquatInputs:
    """One vessel, one channel section, one speed."""

    speed_through_water_kn: float
    draft_m: float
    beam_m: float
    lpp_m: float
    block_coefficient: float = 0.85
    water_depth_m: float = 0.0            # bed to still-water surface
    channel_area_m2: float = 0.0          # wetted section of the CHANNEL; 0 = open water
    displacement_m3: float = 0.0          # 0 -> estimated from Cb x L x B x T
    safety_margin_m: float = DEFAULT_SAFETY_MARGIN_M

    def __post_init__(self):
        if self.speed_through_water_kn < 0:
            raise ValueError("speed_through_water_kn must be >= 0")
        for name in ("draft_m", "beam_m", "lpp_m"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if not 0.3 <= self.block_coefficient <= 1.0:
            raise ValueError("block_coefficient outside 0.3-1.0")


@dataclass
class SquatResult:
    method: str
    squat_m: float                  # the adopted (larger) estimate
    squat_barrass_m: float
    squat_icorels_m: Optional[float]
    blockage_ratio: float
    froude_depth: float
    static_ukc_m: float             # water depth - static draft
    dynamic_ukc_m: float            # what is left under the keel at speed
    grounds: bool
    checks: List[Check] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def _barrass(cb: float, blockage: float, v_kn: float) -> float:
    # Zero blockage is OPEN WATER, where the Barrass confined-channel form does not apply and
    # the answer is zero, not an epsilon. Flooring the blockage at 1e-9 returned 1.6e-07 m,
    # which is a number pretending to be a measurement.
    if v_kn <= 0 or blockage <= 0:
        return 0.0
    return cb * (blockage ** 0.81) * (v_kn ** 2.08) / 20.0


def _icorels(vol_m3: float, lpp: float, fnh: float) -> Optional[float]:
    """None above the validity limit rather than a number that means nothing."""
    if fnh <= 0:
        return 0.0
    if fnh >= 0.99:
        return None
    return 2.4 * (vol_m3 / (lpp ** 2)) * (fnh ** 2) / math.sqrt(1.0 - fnh ** 2)


def compute(inp: SquatInputs) -> SquatResult:
    """Maximum squat by two methods; the LARGER is adopted."""
    v_ms = inp.speed_through_water_kn * 0.514444
    vol = inp.displacement_m3 or (inp.block_coefficient * inp.lpp_m * inp.beam_m * inp.draft_m)
    midship = inp.beam_m * inp.draft_m
    blockage = (midship / inp.channel_area_m2) if inp.channel_area_m2 > 0 else 0.0
    fnh = (v_ms / math.sqrt(GRAVITY * inp.water_depth_m)) if inp.water_depth_m > 0 else 0.0

    s_b = _barrass(inp.block_coefficient, blockage, inp.speed_through_water_kn)
    s_i = _icorels(vol, inp.lpp_m, fnh) if inp.water_depth_m > 0 else None

    cands = [("Barrass II", s_b)] + ([("ICORELS", s_i)] if s_i is not None else [])
    method, squat = max(cands, key=lambda t: t[1])

    static = inp.water_depth_m - inp.draft_m if inp.water_depth_m > 0 else float("inf")
    dynamic = static - squat

    checks: List[Check] = []
    warns: List[str] = []

    checks.append(Check(
        "keel_clears_bed", dynamic > 0,
        f"dynamic UKC {dynamic:.2f} m = static {static:.2f} m - squat {squat:.2f} m "
        f"({method}) at {inp.speed_through_water_kn:.2f} kn"))
    checks.append(Check(
        "keel_clears_bed_with_margin", dynamic >= inp.safety_margin_m,
        f"dynamic UKC {dynamic:.2f} m against a {inp.safety_margin_m:.2f} m working margin",
        severity="warning"))
    checks.append(Check(
        "froude_depth_subcritical", fnh < FNH_VALID_MAX,
        f"depth Froude {fnh:.2f}; above {FNH_VALID_MAX} the flow approaches critical and "
        f"both squat forms lose validity", severity="warning"))
    if blockage > 0:
        checks.append(Check(
            "blockage_within_barrass_range", blockage <= 0.35,
            f"blockage {blockage:.3f}; Barrass is fitted below about 0.35 and extrapolates "
            f"above it", severity="warning"))
    if s_i is not None and s_b > 0:
        spread = abs(s_i - s_b) / max(s_b, 1e-9)
        checks.append(Check(
            "methods_agree_within_50pct", spread <= 0.5,
            f"Barrass {s_b:.2f} m vs ICORELS {s_i:.2f} m, {spread*100:.0f}% apart",
            severity="warning"))
    if s_i is None and fnh > 0:
        warns.append(f"ICORELS not evaluated: depth Froude {fnh:.2f} at or above 0.99")
    if inp.channel_area_m2 <= 0:
        warns.append("no channel area given, so blockage is 0 and Barrass returns 0 — this is "
                     "the OPEN-WATER case and squat is then ICORELS only")

    return SquatResult(method=method, squat_m=squat, squat_barrass_m=s_b, squat_icorels_m=s_i,
                       blockage_ratio=blockage, froude_depth=fnh, static_ukc_m=static,
                       dynamic_ukc_m=dynamic, grounds=dynamic <= 0,
                       checks=checks, warnings=warns)


def max_speed_for_ukc(draft_m: float, beam_m: float, lpp_m: float, water_depth_m: float,
                      channel_area_m2: float, block_coefficient: float = 0.85,
                      safety_margin_m: float = DEFAULT_SAFETY_MARGIN_M,
                      v_hi_kn: float = 20.0, tol_kn: float = 0.01) -> float:
    """The greatest speed through water that keeps ``safety_margin_m`` under the keel.

    Bisection on :func:`compute`, so it uses whichever method is governing rather than
    inverting one formula analytically. Returns 0.0 if the vessel cannot float clear at rest.
    """
    static = water_depth_m - draft_m
    if static <= safety_margin_m:
        return 0.0

    def ukc(v):
        return compute(SquatInputs(speed_through_water_kn=v, draft_m=draft_m, beam_m=beam_m,
                                   lpp_m=lpp_m, block_coefficient=block_coefficient,
                                   water_depth_m=water_depth_m,
                                   channel_area_m2=channel_area_m2)).dynamic_ukc_m

    lo, hi = 0.0, v_hi_kn
    if ukc(hi) >= safety_margin_m:
        return hi
    while hi - lo > tol_kn:
        mid = 0.5 * (lo + hi)
        if ukc(mid) >= safety_margin_m:
            lo = mid
        else:
            hi = mid
    return lo
