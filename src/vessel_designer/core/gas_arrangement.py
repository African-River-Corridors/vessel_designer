"""Best gas-tank arrangement for a hull: search, don't trust the single AUTO answer.

Rebuilt natively from an earlier project wrapper, fixing three defects (numbered 1, 3, 4
in the original defect list) at the engine boundary:

1. ``barge_capacity``'s clearance loop has two self-consistent roots at some beams and its
   seed can land on the worse one (CN II at 14.8 m: AUTO 2 abreast ~1,156 t against
   1 abreast 2,058 t). So every tanks-abreast count is forced and converged on its own.
3. The engine fills the beam with the largest tank allowed. Under a draught cap more tank is
   more steel, and steel displaces cargo, so smaller-tank variants (extra side clearance,
   never below the code minimum) are also tried. A tank over the OD cap is re-tried ON the cap
   with the clearance widened -- and REJECTED if that clearance is below the rule for its volume.
4. Tanks in line were fixed at 2. Under ADN type G each tank is capped in volume and in L/D,
   so tanks are added along the hull until they comply.

Moulded depth is not set by the waterway, so it is swept and the depth that carries the most
per journey at the draught cap is kept -- among the candidates that PASS their error-severity
checks. A candidate that carries more but is overloaded or has no freeboard never wins. If no
candidate passes, the best-tonnage one is returned with ``feasible=False`` and its failed checks
listed (the module's convention: report through checks, don't raise). Every setting is an explicit argument -- no module
globals (the wrapper's ``use_settings()`` was a stop-gap).

Pure calculation, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional, Sequence

from .checks import all_ok
from .barge_capacity import MAX_TANK_OD_M, BargeCapacityInputs, compute as capacity
from .journey_derating import JourneyDeratingInputs, compute as derate
from .protective_location import (ADN_G_MAX_L_OVER_D, ADN_G_TANK_CAP_9_3_4_M3,
                                  ADN_G_WIDE_TANK_FRACTION, compute_required_clearances,
                                  d_vc_exact, distance_d_vc)

RULESETS = ("IGC_2G", "IGC_2G_EXACT", "ADN_G")
DEFAULT_DEPTHS_M = tuple(round(3.5 + 0.25 * i, 2) for i in range(15))     # 3.5 .. 7.0 m
DEFAULT_TANKS_WIDE = (1, 2, 3)
DEFAULT_EXTRA_CLEARANCE_M = (0.5, 1.0, 1.5, 2.0)
ADN_LONGITUDINAL_GAP_M = 2.0      # tank-to-tank gap the engine uses along the hull (a default, not a rule)


@dataclass
class ArrangementFit:
    loa_m: float
    beam_m: float
    depth_m: float
    cargo: str
    ruleset: str
    fill_ratio: float
    self_propelled: bool
    t_max_m: float
    payload_t: float              # per journey, after the draught cap
    volume_capacity_t: float
    binding: str                  # "volume" | "draft" | "no cargo area"
    draft_at_payload_m: float
    cargo_zone_m: float
    stern_void_m: float
    bow_void_m: float
    tank_od_m: float
    n_tanks: int
    n_tanks_wide: int
    n_tanks_long: int
    lightship_t: float
    air_draft_light_m: float
    side_clearance_m: float = 0.0
    tank_inner_diameter_m: float = 0.0
    containment_inner_volume_m3: float = 0.0
    per_tank_volume_m3: float = 0.0
    cargo_volume_m3: float = 0.0
    density_t_m3: float = 0.0
    failed_checks: list = field(default_factory=list)
    feasible: bool = True         # False: no candidate passed its error checks; see failed_checks
    candidates_tried: int = 0
    # The engine's own objects, for the GA generator. Not serialised.
    engine_inputs: object = field(default=None, repr=False, compare=False)
    engine_result: object = field(default=None, repr=False, compare=False)


def required_side_clearance(ruleset: str, beam: float, total_m3: float, per_tank_m3: float,
                            insulation_mm: float) -> float:
    """The code minimum for the engine's clearance datum (outer face of the insulation)."""
    if ruleset == "IGC_2G_EXACT":      # per-tank d, measured to steel: insulation sits inside d
        return d_vc_exact(per_tank_m3) - insulation_mm / 1000.0
    return compute_required_clearances(ruleset, beam, distance_d_vc(total_m3)).cs_required


def fit(loa: float, beam: float, cargo: str, t_max: float, *, ruleset: str = "IGC_2G",
        fill_ratio: float = 0.95, self_propelled: bool = True,
        depths: Sequence[float] = DEFAULT_DEPTHS_M, tanks_wide: Sequence[int] = DEFAULT_TANKS_WIDE,
        extra_clearance_m: Sequence[float] = DEFAULT_EXTRA_CLEARANCE_M,
        adn_tank_cap_m3: float = ADN_G_TANK_CAP_9_3_4_M3, block_coefficient: float = 0.85,
        max_tank_od_m: float = MAX_TANK_OD_M) -> ArrangementFit:
    """Most cargo per journey at draught cap ``t_max`` over depth x arrangement.

    Only candidates whose error-severity checks all pass can win. If none passes, the
    best-tonnage candidate comes back with ``feasible=False``; check it before using the payload.
    """
    if ruleset not in RULESETS:
        raise ValueError(f"ruleset must be one of {RULESETS}")
    base = dict(loa=loa, beam=beam, cargo_type=cargo, self_propelled=self_propelled,
                vessel_type=ruleset, fill_ratio=fill_ratio, block_coefficient=block_coefficient)
    tried = 0

    def build(d: float, nw: int, nl: int):
        nonlocal tried
        tried += 1
        inp = BargeCapacityInputs(depth=float(d), n_tanks_wide=nw, n_tanks_long=nl, **base)
        r = capacity(inp)
        if not r.tank_outer_diameter_m or r.tank_outer_diameter_m > max_tank_od_m + 1e-6:
            # Full-beam tank infeasible or over the cap: put the tank ON the cap and widen the
            # clearance -- a legitimate design only if that clearance meets the rule.
            cs = (beam - nw * max_tank_od_m) / 2.0
            if cs < 0:
                return None
            inp = replace(inp, side_clearance_override_m=cs)
            r = capacity(inp)
            if not r.tank_outer_diameter_m or r.tank_outer_diameter_m > max_tank_od_m + 1e-6:
                return None
            total = r.containment_inner_volume_m3 or 0.0
            need = required_side_clearance(ruleset, beam, total, total / max(r.n_tanks_total or 1, 1),
                                           r.insulation_thickness_mm or 0.0)
            if cs + 1e-9 < need:
                return None
        if ruleset == "ADN_G":
            per_tank = (r.containment_inner_volume_m3 or 0.0) / max(r.n_tanks_total or 1, 1)
            tank_len = ((r.cargo_zone_length_m or 0.0) - (nl - 1) * ADN_LONGITUDINAL_GAP_M) / nl
            if per_tank > adn_tank_cap_m3 + 1e-6 or tank_len > ADN_G_MAX_L_OVER_D * r.tank_outer_diameter_m:
                return None
        return inp, r

    best = None           # best candidate that passes its error checks
    best_any = None       # best candidate overall: reported only if none passes
    for d in depths:
        for nw in tanks_wide:
            if ruleset == "ADN_G":
                # Add tanks along the hull until one complies, then one more (shorter tanks lose
                # head length but can balance better).
                cands = []
                for nl in range(2, 25):
                    x = build(d, nw, nl)
                    if x is not None:
                        cands.append(x)
                        if len(cands) == 2:
                            break
            else:
                x = build(d, nw, 2)
                cands = [x] if x is not None else []
            more = []
            for inp0, r0 in cands:
                if not r0.tank_outer_diameter_m or r0.side_clearance_m is None:
                    continue
                for extra in extra_clearance_m:
                    tried += 1
                    i2 = replace(inp0, side_clearance_override_m=r0.side_clearance_m + extra)
                    r2 = capacity(i2)
                    if r2.tank_outer_diameter_m and r2.cargo_capacity_t > 0:
                        more.append((i2, r2))
            for inp, r in cands + more:
                j = derate(JourneyDeratingInputs(capacity=r, loa=loa, beam=beam, depth=float(d),
                                                 block_coefficient=block_coefficient,
                                                 design_depth_m=t_max, ukc_m=0.0))
                cand = (j.achievable_tonnage_t, d, r, j, inp)
                if best_any is None or j.achievable_tonnage_t > best_any[0] + 1e-6:
                    best_any = cand
                if all_ok(r.checks + j.checks) and (best is None or j.achievable_tonnage_t > best[0] + 1e-6):
                    best = cand

    if best is None:   # nothing passes: report the best failing candidate, flagged infeasible
        best = best_any
    if best is None:   # nothing fitted: report the plain single-tank attempt, which carries nothing
        d = float(depths[0])
        inp = BargeCapacityInputs(depth=d, n_tanks_wide=1, **base)
        r = capacity(inp)
        j = derate(JourneyDeratingInputs(capacity=r, loa=loa, beam=beam, depth=d,
                                         block_coefficient=block_coefficient,
                                         design_depth_m=t_max, ukc_m=0.0))
        best = (0.0, d, r, j, inp)

    _, d, r, j, inp = best
    n_total = int(r.n_tanks_total or 0)
    n_wide = int(r.n_tanks_wide or 0)
    failed = [f"{c.name}: {c.message}" for c in r.checks + j.checks if not c.ok]
    feasible = all_ok(r.checks + j.checks)
    if ruleset == "ADN_G" and (r.tank_outer_diameter_m or 0) > ADN_G_WIDE_TANK_FRACTION * beam:
        failed.append(f"adn_wide_tank: tank {r.tank_outer_diameter_m:.1f} m > 0.70 B; "
                      "ADN 9.3.1.14.2 needs extra intact stability checks")
    return ArrangementFit(
        loa_m=loa, beam_m=beam, depth_m=float(d), cargo=cargo, ruleset=ruleset,
        fill_ratio=fill_ratio, self_propelled=self_propelled, t_max_m=t_max,
        payload_t=float(j.achievable_tonnage_t), volume_capacity_t=float(r.cargo_capacity_t),
        binding="no cargo area" if r.cargo_capacity_t <= 0 else j.binding_limit,
        draft_at_payload_m=float(j.draft_at_achievable_m),
        cargo_zone_m=float(r.cargo_zone_length_m or 0.0),
        stern_void_m=float(r.stern_void_length_m or 0.0), bow_void_m=float(r.bow_void_length_m or 0.0),
        tank_od_m=float(r.tank_outer_diameter_m or 0.0), n_tanks=n_total, n_tanks_wide=n_wide,
        n_tanks_long=(n_total // n_wide) if n_wide else 0, lightship_t=float(r.lightship_t),
        air_draft_light_m=float(r.air_draft_light_m or r.air_draft_m),
        side_clearance_m=float(r.side_clearance_m or 0.0),
        tank_inner_diameter_m=float(r.tank_inner_diameter_m or 0.0),
        containment_inner_volume_m3=float(r.containment_inner_volume_m3 or 0.0),
        per_tank_volume_m3=float((r.containment_inner_volume_m3 or 0.0) / max(n_total, 1)),
        cargo_volume_m3=float(r.cargo_volume_m3), density_t_m3=float(r.cargo_density_t_per_m3),
        failed_checks=failed, feasible=feasible, candidates_tried=tried, engine_inputs=inp, engine_result=r)


def smallest_viable_loa(beam: float, cargo: str, t_max: float, *, lo: float = 20.0,
                        hi: float = 120.0, **kw) -> float:
    """Shortest LOA (to 0.1 m) at which the hull has any cargo area at all."""
    kw.setdefault("depths", (DEFAULT_DEPTHS_M[0],))
    if fit(hi, beam, cargo, t_max, **kw).volume_capacity_t <= 0:
        return float("inf")
    while hi - lo > 0.1:
        mid = 0.5 * (lo + hi)
        if fit(mid, beam, cargo, t_max, **kw).volume_capacity_t > 0:
            hi = mid
        else:
            lo = mid
    return round(hi, 1)
