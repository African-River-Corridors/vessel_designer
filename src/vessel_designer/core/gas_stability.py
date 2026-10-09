"""Intact stability of a gas barge: GM, the GZ curve and the code criteria (defect 8).

Tall IMO Type C tanks on a shallow hull are exactly where intact stability bites, and the
gas branch had no check at all. This module takes a converged gas arrangement
(``BargeCapacityResult.gas_basis``) and assesses three loading conditions:

  * laden    -- the payload actually carried (after any draught cap), so the tanks may be
                partly filled and their free surface is the real one;
  * half     -- half that payload: the worst free surface for a horizontal cylinder;
  * light    -- lightship, tanks empty: the highest KG relative to displacement.

Method (concept stage, stated on every result):
  * Hull is a prismatic box section (no rakes), the same idealisation the capacity chain uses.
    Draught at a displacement follows Cb x L x B x T x rho, as in ``barge_capacity``.
  * GZ is computed EXACTLY for the heeled box section (polygon clipping), so it stays valid
    past deck-edge immersion and bilge emergence. No downflooding openings are modelled.
  * Cargo free surface: liquid height is solved from the fill VOLUME fraction (circular
    segment), not taken as a height ratio. GZ_fluid = GZ_solid - FSC x sin(phi).
  * KG from the weight split: hull steel at 0.5 D, tanks + insulation + cargo at their own
    heights, piping at deck, outfitting at 0.75 D. These are first-order positions.
  * Not included: the self-propelled stern block's mass (it is not in the gas lightship either),
    wind heel, damage stability. Each is stated as a limitation.

Criteria sets:
  * ``IS_CODE_2008`` -- IMO Intact Stability Code 2008, Part A 2.2 (the general criteria IGC
    ch. 2 relies on). Seagoing; an inland administration may accept less.
  * ``ADN_9_3_1_14_2`` -- ADN 2025 9.3.1.14.2, applies when a cargo tank is wider than 0.70 B:
    GM >= 0.10 m, GZ >= 0.10 m and area >= 0.024 m.rad up to 27 deg. Values as transcribed in
    the Ankobra tank-rules research note; confirm against the ADN text before release.

Pure calculation, no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

ANGLES_DEG = tuple(range(0, 61))


# --- geometry helpers -----------------------------------------------------------------------

def _clip_below(poly, h):
    """Sutherland-Hodgman: keep the part of polygon `poly` (list of (Y, Z)) with Z <= h."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        pin, qin = p[1] <= h, q[1] <= h
        if pin:
            out.append(p)
        if pin != qin:
            t = (h - p[1]) / (q[1] - p[1])
            out.append((p[0] + t * (q[0] - p[0]), h))
    return out


def _area_centroid(poly):
    a = cy = cz = 0.0
    n = len(poly)
    for i in range(n):
        (y0, z0), (y1, z1) = poly[i], poly[(i + 1) % n]
        c = y0 * z1 - y1 * z0
        a += c
        cy += (y0 + y1) * c
        cz += (z0 + z1) * c
    a *= 0.5
    if abs(a) < 1e-12:
        return 0.0, 0.0, 0.0
    return abs(a), cy / (6 * a), cz / (6 * a)


def box_gz(beam: float, depth: float, draught: float, kg: float, phi_deg: float) -> float:
    """Righting lever (m) of a box section heeled phi, at constant displaced area B x T."""
    if phi_deg == 0:
        return 0.0
    phi = math.radians(phi_deg)
    c, s = math.cos(phi), math.sin(phi)
    hull = [(-beam / 2, 0.0), (beam / 2, 0.0), (beam / 2, depth), (-beam / 2, depth)]
    rot = [(y * c - z * s, y * s + z * c) for y, z in hull]     # earth frame; +phi lifts starboard
    target = beam * draught
    zs = [p[1] for p in rot]
    lo, hi = min(zs), max(zs)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        a, _, _ = _area_centroid(_clip_below(rot, mid))
        lo, hi = (mid, hi) if a < target else (lo, mid)
    _, yb, _ = _area_centroid(_clip_below(rot, 0.5 * (lo + hi)))
    yg = -kg * s                     # G in the earth frame
    return yg - yb                   # positive = righting


def segment_fill(radius: float, volume_fraction: float):
    """Liquid height h (from tank bottom) and centroid height for a horizontal cylinder
    filled to `volume_fraction` of its cross-section area."""
    f = min(max(volume_fraction, 0.0), 1.0)
    if f <= 0:
        return 0.0, 0.0
    if f >= 1:
        return 2 * radius, radius
    lo, hi = 0.0, math.pi
    for _ in range(80):              # theta = central angle of the segment: A = r^2 (t - sin t) / 2
        t = 0.5 * (lo + hi)
        if (t - math.sin(t)) / (2 * math.pi) < f:
            lo = t
        else:
            hi = t
    t = 0.5 * (lo + hi)
    h = radius * (1 - math.cos(t / 2))
    area = radius ** 2 * (t - math.sin(t)) / 2
    ybar_from_centre = (4 * radius * math.sin(t / 2) ** 3) / (3 * (t - math.sin(t)))
    return h, radius - ybar_from_centre if area > 0 else 0.0


# --- results ----------------------------------------------------------------------------

@dataclass
class Criterion:
    name: str
    value: float
    limit: float
    ok: bool
    source: str


@dataclass
class Condition:
    name: str
    cargo_t: float
    fill_fraction: float
    displacement_t: float
    draught_m: float
    kg_m: float
    gm_solid_m: float
    free_surface_m: float
    gm_fluid_m: float
    gz: list                          # [(deg, GZ_fluid m)]
    max_gz_m: float
    max_gz_deg: float
    area_0_27: float
    area_0_30: float
    area_0_40: float
    area_30_40: float
    deck_edge_deg: Optional[float]
    criteria: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.criteria)


@dataclass
class StabilityAssessment:
    criteria_set: str
    conditions: list
    limitations: list

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.conditions)

    @property
    def governing(self) -> Condition:
        return min(self.conditions, key=lambda c: c.gm_fluid_m)


def _area(gz, a0, a1):
    pts = [(d, g) for d, g in gz if a0 <= d <= a1]
    return sum(0.5 * (g0 + g1) * math.radians(d1 - d0) for (d0, g0), (d1, g1) in zip(pts, pts[1:]))


def _criteria(cset: str, c: "Condition", wide_tank: bool) -> list:
    gz_at = dict(c.gz)
    if cset == "IS_CODE_2008":
        src = "IMO IS Code 2008, Part A 2.2"
        gz_30_plus = max(g for d, g in c.gz if d >= 30)
        return [
            Criterion("Area 0–30°", c.area_0_30, 0.055, c.area_0_30 >= 0.055, src + ".1"),
            Criterion("Area 0–40°", c.area_0_40, 0.090, c.area_0_40 >= 0.090, src + ".1"),
            Criterion("Area 30–40°", c.area_30_40, 0.030, c.area_30_40 >= 0.030, src + ".1"),
            Criterion("GZ at ≥ 30°", gz_30_plus, 0.20, gz_30_plus >= 0.20, src + ".2"),
            Criterion("Angle of max GZ", c.max_gz_deg, 25.0, c.max_gz_deg >= 25.0, src + ".3"),
            Criterion("Initial GM (fluid)", c.gm_fluid_m, 0.15, c.gm_fluid_m >= 0.15, src + ".4"),
        ]
    if cset == "ADN_9_3_1_14_2":
        src = "ADN 2025 9.3.1.14.2 (tank > 0.70 B)"
        if not wide_tank:
            return [Criterion("Initial GM (fluid) > 0", c.gm_fluid_m, 0.0, c.gm_fluid_m > 0,
                              "ADN 9.3.1.14.1 — no tank wider than 0.70 B, so 9.3.1.14.2 does not apply")]
        gz_max_27 = max(g for d, g in c.gz if d <= 27)
        return [
            Criterion("Initial GM (fluid)", c.gm_fluid_m, 0.10, c.gm_fluid_m >= 0.10, src),
            Criterion("GZ within 27°", gz_max_27, 0.10, gz_max_27 >= 0.10, src),
            Criterion("Area 0–27°", c.area_0_27, 0.024, c.area_0_27 >= 0.024, src),
        ]
    raise ValueError(f"unknown criteria set {cset!r}")


def criteria_set_for(ruleset: str) -> str:
    return "ADN_9_3_1_14_2" if ruleset == "ADN_G" else "IS_CODE_2008"


def assess(result, payload_t: float, *, block_coefficient: float = 0.85,
           water_density: float = 1.0, criteria_set: str = "IS_CODE_2008") -> StabilityAssessment:
    """Assess a converged gas arrangement (a ``BargeCapacityResult`` with ``gas_basis``)."""
    basis = result.gas_basis
    if basis is None:
        raise ValueError("assess() needs a gas BargeCapacityResult (gas_basis is None)")
    bi, tanks, w = basis["inputs"], basis["tanks"], basis["weights"]
    L, B, D = bi.loa, bi.beam, bi.depth
    rho_c = result.cargo_density_t_per_m3
    od, r_in = tanks.outer_diameter, tanks.inner_diameter / 2.0
    tank_bottom = bi.double_bottom_height + bi.tank_support_height        # outer face, above keel
    kg_tank = tank_bottom + od / 2.0
    inner_bottom = tank_bottom + (od / 2.0 - r_in)
    v_inner_total = tanks.total_tank_volume
    wide_tank = od > 0.70 * B

    light_items = [                                        # (t, KG m)
        (w.steel_top_down, 0.5 * D),
        (w.tank_total + w.insulation, kg_tank),
        (w.piping_machinery, D),
        (w.outfitting, 0.75 * D),
    ]
    lightship = sum(m for m, _ in light_items)

    conds = []
    for name, cargo in (("Laden", payload_t), ("Half laden", 0.5 * payload_t), ("Light", 0.0)):
        frac = cargo / (rho_c * v_inner_total) if v_inner_total > 0 else 0.0
        h, ybar = segment_fill(r_in, frac)
        kg_cargo = inner_bottom + ybar
        items = light_items + ([(cargo, kg_cargo)] if cargo > 0 else [])
        disp = sum(m for m, _ in items)
        kg = sum(m * z for m, z in items) / disp
        T = disp / (block_coefficient * L * B * water_density)
        if T >= D:
            conds.append(Condition(name, cargo, frac, disp, T, kg, -1, 0, -1, [], 0, 0, 0, 0, 0, 0, None,
                                   [Criterion("Floats with freeboard", T, D, False, "draught ≥ depth")]))
            continue
        kb, bm = T / 2.0, B * B / (12.0 * T)
        gm_solid = kb + bm - kg
        # Free surface: chord at the liquid level, along the cylindrical length, every tank.
        if 0 < frac < 1:
            chord = 2.0 * math.sqrt(max(r_in ** 2 - (r_in - h) ** 2, 0.0))
            i_fs = tanks.n_tanks_total * tanks.cylinder_length * chord ** 3 / 12.0
        else:
            i_fs = 0.0
        fsc = rho_c * i_fs / disp
        gz = [(a, box_gz(B, D, T, kg, a) - fsc * math.sin(math.radians(a))) for a in ANGLES_DEG]
        max_gz_deg, max_gz = max(gz, key=lambda p: p[1])
        deck_edge = math.degrees(math.atan(2 * (D - T) / B))
        c = Condition(name, cargo, frac, disp, T, kg, gm_solid, fsc, gm_solid - fsc, gz, max_gz,
                      max_gz_deg, _area(gz, 0, 27), _area(gz, 0, 30), _area(gz, 0, 40),
                      _area(gz, 30, 40), deck_edge)
        c.criteria = _criteria(criteria_set, c, wide_tank)
        conds.append(c)

    limitations = [
        "Concept-stage: prismatic box section, first-order weight heights, no downflooding openings.",
        "No wind heel and no damage stability (ADN 9.3.1.15 / IGC 2.7 need both before approval).",
    ]
    if getattr(result, "aft_arrangement", None) is not None:
        limitations.append("The self-propelled stern block's mass is not in the gas lightship, so KG "
                           "and displacement leave it out; the true GM could be lower.")
    if abs(lightship - result.lightship_t) > 1.0:
        limitations.append(f"Weight split sums to {lightship:.0f} t vs lightship {result.lightship_t:.0f} t.")
    return StabilityAssessment(criteria_set, conds, limitations)
