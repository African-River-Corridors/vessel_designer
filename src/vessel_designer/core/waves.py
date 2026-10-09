"""Added resistance in waves — the sea leg, not the river.

WHY THIS MODULE EXISTS. `resistance.py` has no wave term at all. Asked what the NGL vessel
would do on the 43.2 nm run from the Ankobra mouth to Takoradi in 1 m waves, the only honest
answer was "the engine computes calm water; here is a sea margin I chose". A margin picked by
the analyst is not a model, and it is exactly the kind of number that later gets quoted as
though it had been calculated.

THE METHOD: STAwave-1
---------------------
ITTC's recommended simple estimate of added resistance in HEAD waves, used where a full
seakeeping computation is not available::

    R_AWL = (1/16) * rho * g * H_s^2 * B * sqrt(B / L_BWL)

  H_s      significant wave height (m)
  B        beam at the waterline (m)
  L_BWL    length of the bow section on the waterline, from the stem to 95% of maximum beam

It is deliberately crude: it depends on the bow only, not on the wave period, the heading or
the speed. That is its strength for a screening estimate and its limit for anything else.

ITTC states the validity condition as heave and pitch being small, which in practice means::

    lambda / L_pp  <  0.5      (short waves relative to the ship)

Outside that the ship responds to the waves, added resistance rises sharply through the
resonance region around lambda/L_pp ~ 1, and STAwave-1 UNDER-predicts — often by a factor of
two or more. The result carries that as a failed check rather than a footnote, because on a
90 m hull in a swell of any length the condition is usually NOT met.

HEADING
-------
Added resistance falls off away from head seas. A common screening treatment is a cosine-type
factor on the heading; here it is ``max(0, cos(mu))^2`` with ``mu`` the angle off the bow, so
beam seas give zero added resistance from this term. That is optimistic — beam seas add
resistance through drift and rudder action, which this does not model — so a beam-sea answer
from this module should be treated as a floor.

WHAT THIS DOES NOT DO
---------------------
* No wind. A separate and often larger term for a light, high-sided vessel.
* No drift, rudder or course-keeping loss, which dominates in quartering seas.
* No voluntary speed reduction: it says what the added resistance IS, not what a master would
  choose to do about slamming or deck wetness.
* No swell-vs-windsea distinction; H_s is taken as one number.
* Nothing about whether the vessel is CLASSED for the exposure. An inland hull in 1 m waves
  is a certification question, not a resistance one.

Pure functions, math only — Pyodide-safe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from .checks import Check, all_ok

GRAVITY = 9.80665
SEAWATER_DENSITY_T_M3 = 1.025

#: ITTC's stated validity for STAwave-1: waves short relative to the hull.
LAMBDA_OVER_LPP_MAX = 0.5


@dataclass(frozen=True)
class WaveResistanceInputs:
    significant_wave_height_m: float
    beam_waterline_m: float
    lpp_m: float
    #: Bow length on the waterline, stem to 95% of max beam. Defaults to 0.2*Lpp, which suits
    #: a BLUNT inland barge bow; a fine seagoing bow is nearer 0.3*Lpp and gives LESS added
    #: resistance, so the default is the conservative one for this fleet.
    bow_waterline_length_m: float = 0.0
    heading_deg_off_bow: float = 0.0
    peak_wave_period_s: float = 0.0        # 0 -> estimated from H_s
    water_density_t_m3: float = SEAWATER_DENSITY_T_M3
    speed_kn: float = 0.0                  # carried for reporting; STAwave-1 is speed-free

    def __post_init__(self):
        if self.significant_wave_height_m < 0:
            raise ValueError("significant_wave_height_m must be >= 0")
        for n in ("beam_waterline_m", "lpp_m"):
            if getattr(self, n) <= 0:
                raise ValueError(f"{n} must be > 0")
        if not 0.0 <= self.heading_deg_off_bow <= 180.0:
            raise ValueError("heading_deg_off_bow must be 0-180")


@dataclass
class WaveResistanceResult:
    added_resistance_kn: float
    added_resistance_head_seas_kn: float   # before the heading factor
    heading_factor: float
    bow_waterline_length_m: float
    wavelength_m: float
    lambda_over_lpp: float
    added_power_kw: float                  # at the quoted speed, effective (thrust) power
    checks: List[Check] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def _peak_period(hs: float) -> float:
    """A fetch-limited-sea estimate, T_p ~ 4.0*sqrt(H_s), used only to report lambda/Lpp
    when no period is supplied. It is an ESTIMATE and the validity check says so."""
    return 4.0 * math.sqrt(hs) if hs > 0 else 0.0


def compute(inp: WaveResistanceInputs) -> WaveResistanceResult:
    hs = inp.significant_wave_height_m
    b = inp.beam_waterline_m
    lbwl = inp.bow_waterline_length_m or (0.2 * inp.lpp_m)
    rho = inp.water_density_t_m3 * 1000.0        # t/m3 -> kg/m3

    # STAwave-1, head seas. rho*g*Hs^2*B in N; /1000 -> kN
    r_head = (1.0 / 16.0) * rho * GRAVITY * (hs ** 2) * b * math.sqrt(b / lbwl) / 1000.0

    mu = math.radians(inp.heading_deg_off_bow)
    # cos(90 deg) is 6.1e-17 in floating point, not 0, which returned 3e-32 kN of added
    # resistance in beam seas. Snap it: abeam and abaft the beam this term is ZERO, and a
    # residue of 1e-32 is a number pretending to be a measurement. (Second time today; the
    # Barrass blockage floor did the same thing.)
    _c = math.cos(mu)
    hf = 0.0 if _c <= 1e-12 else _c ** 2
    r = r_head * hf

    tp = inp.peak_wave_period_s or _peak_period(hs)
    lam = (GRAVITY * tp ** 2) / (2.0 * math.pi) if tp > 0 else 0.0
    lol = lam / inp.lpp_m if inp.lpp_m > 0 else 0.0

    v_ms = inp.speed_kn * 0.514444
    added_kw = r * v_ms      # kN * m/s = kW, effective (thrust) power

    checks: List[Check] = []
    warns: List[str] = []

    checks.append(Check(
        "stawave1_short_wave_validity", 0.0 < lol < LAMBDA_OVER_LPP_MAX,
        f"lambda/Lpp = {lol:.2f} (lambda {lam:.0f} m on Lpp {inp.lpp_m:.0f} m). STAwave-1 "
        f"assumes short waves, lambda/Lpp < {LAMBDA_OVER_LPP_MAX}; outside that it "
        f"UNDER-predicts, and near lambda/Lpp = 1 it can do so by more than 2x",
        severity="warning"))
    checks.append(Check(
        "wave_height_within_screening_range", hs <= 3.0,
        f"H_s {hs:.2f} m; above about 3 m a screening formula is not the right tool and "
        f"voluntary speed reduction usually governs anyway", severity="warning"))
    checks.append(Check(
        "bow_length_supplied", inp.bow_waterline_length_m > 0,
        f"L_BWL not given, assumed {lbwl:.1f} m = 0.2 x Lpp (a blunt barge bow). A finer bow "
        f"reduces added resistance, so this is the conservative assumption",
        severity="warning"))
    if inp.peak_wave_period_s <= 0 and hs > 0:
        warns.append(f"no wave period given; T_p estimated at {tp:.1f} s from H_s, which sets "
                     f"only the validity check, not the resistance")
    if inp.heading_deg_off_bow > 60.0:
        warns.append("beam-ish seas: this module returns a FLOOR, because drift, rudder and "
                     "course-keeping loss is not modelled and it dominates off the bow")

    return WaveResistanceResult(
        added_resistance_kn=r, added_resistance_head_seas_kn=r_head, heading_factor=hf,
        bow_waterline_length_m=lbwl, wavelength_m=lam, lambda_over_lpp=lol,
        added_power_kw=added_kw, checks=checks, warnings=warns)
