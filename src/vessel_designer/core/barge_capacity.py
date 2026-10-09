"""Unified barge design & volume-bound cargo capacity.

Single source of truth for turning a scenario (LOA, beam, moulded depth, cargo type)
plus design assumptions into a barge design and its three headline outputs:

    - cargo_capacity_t      volume-bound tonnage (tanks/hold full at fill ratio)
    - full_load_draft_m     equilibrium draft carrying that cargo
    - air_draft_m           LADEN air draft: tallest fixed point above keel, minus the
                            full-load draft
    - air_draft_light_m     LIGHT air draft: the same top, minus the LIGHTSHIP draft.
                            This is the GOVERNING case for bridge clearance -- an empty
                            barge floats high, so it is always the larger of the two.
                            Gate on this, never on air_draft_m. Added 2026-09-16 after a
                            review found every air-draft figure in the model was the
                            favourable laden case.

Handles cryogenic gas (IGC/IGF Type-C tanks) and bauxite (trapezoidal hopper hold).

NOTE — capacity here is VOLUME-BOUND only. The weight/draft limit (channel depth − UKC)
is NOT applied in this module; it is applied downstream at the scenario / channel-design
stage, which re-derives the achievable per-journey tonnage from the actual channel.

Full design basis, worked examples and grid sweep:
    docs/feasibility/barge-cargo-chain.md

Pure Python apart from the hull (numpy) — runs client-side in Pyodide.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Optional

from .aft_arrangement import (AftArrangementInputs, AftArrangementResult,
                              compute as compute_aft_arrangement)
from .cargo import get_cargo
from .checks import Check, all_ok
from .gas_separation import (GasSeparationInputs, GasSeparationResult,
                             compute as compute_gas_separation)
from .hull import HullGeometry
from .hydrostatics import find_equilibrium_draft
from .models import BargeInputs
from .protective_location import compute_required_clearances, distance_d_vc, d_vc_exact
from .tanks import calculate_tank_arrangement
from .weights import calculate_weights


@dataclass
class BargeCapacityInputs:
    """Inputs for the unified barge capacity calculation."""

    # --- Scenario fundamentals ---
    loa: float                          # length overall (m)
    beam: float                         # moulded beam (m)
    depth: float                        # moulded depth (m) — scenario input
    cargo_type: str = "LNG_ethane"      # key into cargo.py (gas or "bauxite")

    # --- Common assumptions ---
    block_coefficient: float = 0.85
    water_density: float = 1.0          # t/m^3 (1.0 fresh, 1.025 salt)
    required_freeboard: float = 0.3     # m, minimum
    # Bridge/air-draft clearance limit (m). When set, `air_draft_within_limit` checks the
    # LIGHT condition against it -- the empty return leg, not the laden one.
    air_draft_limit_m: Optional[float] = None
    # Ballast the empty leg can carry (t). Reduces the light air draft; 0 = unballasted.
    ballast_capacity_t: float = 0.0

    # --- Arrangement (the stern block and the ends of the cargo area) ---
    # DERIVED, not a fraction of LOA. `aft` describes the equipment that has to fit aft
    # (thrusters, battery, accommodation, wheelhouse); `separation` the gas-code distance
    # between the cargo area and that block. Leave both None for the standard vessel.
    aft: Optional[AftArrangementInputs] = None
    separation: Optional[GasSeparationInputs] = None
    # SELF-PROPELLED (default) carries the stern block -- thrusters, battery,
    # accommodation, wheelhouse. A PUSHED (dumb) barge does not: the crew and propulsion
    # sit on the tug, so the cargo hull keeps that length. Set False for a pushed unit.
    #
    # This is the whole architecture question in one flag, and it is worth 19-20 m of hull.
    # Do NOT set it False for CN II: DEC-2026-09-18-ankobra-cn-ii-is-a-motor-vessel says
    # the class's 90 m already includes machinery and accommodation, so a pusher deducts
    # that space twice.
    self_propelled: bool = True
    # Aft void of a PUSHED barge (m): stern rake plus the coupling/steering void. ESTIMATE.
    pushed_stern_void_m: float = 3.0
    # Bow bottom rake (m). None -> 1.6 x moulded depth. ESTIMATE: no rake is surveyed or
    # specified for this vessel; it is carried as an input so it can be replaced, not
    # buried. RFI Q-ANK bow-rake-1.
    bow_rake_length_m: Optional[float] = None
    # Dry-bulk end-bulkhead allowance at each end of the hold (m). The gas branch takes
    # this from `gas_separation` instead.
    bulk_end_bulkhead_m: float = 0.50

    # --- Gas branch (IGC/IGF) ---
    vessel_type: str = "IGC_2G"
    # Optional side-clearance override (m per side). None -> IGC protective-location
    # formula (Cs = d(Vc) for 2G). The report's decided basis (Niall, 1 Jul 2026) is the
    # CONSERVATIVE 12%-of-beam simplification -> pass 0.12*beam here; the code formula
    # gives ~1.0 m and ~20% more cargo (stated in the report as upside).
    side_clearance_override_m: Optional[float] = None
    # None = AUTO: the fewest tanks across that keeps each tank's OD within
    # MAX_TANK_OD_M. Pass an int to force an arrangement.
    n_tanks_wide: Optional[int] = None
    n_tanks_long: int = 2
    tank_wall_thickness: Optional[float] = 25.0  # mm; None = auto pressure-vessel formula
    fill_ratio: float = 0.95
    dome_height: float = 2.0
    tank_support_height: float = 0.5

    # --- Bulk branch ---
    # Hold type sets the lightship method. "sloped_hopper": the plating build-up below
    # (Ankobra bauxite hopper). "box" / "container": a calibrated k x L.B.D for the whole
    # lightship -- calibration pass 1 (2026-10-06) found the build-up 31-111 % heavy on real
    # box-hold barges. k values come from calibration/factors.yaml via the caller.
    hold_type: str = "sloped_hopper"     # "sloped_hopper" | "box" | "container"
    lightship_k_t_per_m3: Optional[float] = None   # required for "box"/"container"
    wing_void_width: float = 1.0        # fixed wing-void width per side (m)
    double_bottom_height_bulk: float = 1.2
    hopper_slope_h_per_v: float = 1.0   # lower-knuckle slope (~45 deg)
    coaming_height: float = 1.0         # hold extends above deck inside coaming (m)
    n_holds: int = 3
    hold_fill_ratio: float = 0.95
    bow_void_fraction: float = 0.10
    stern_void_fraction: float = 0.15
    # bulk steel build-up (plating thicknesses in mm)
    inner_bottom_t_mm: float = 14.0
    hopper_plate_t_mm: float = 14.0
    bulkhead_t_mm: float = 11.0
    coaming_t_mm: float = 10.0
    steel_density: float = 7.85
    bulk_structure_factor: float = 1.40
    bulk_steel_rate_per_cbm: float = 0.10
    bulk_piping_factor: float = 0.04
    bulk_outfitting_factor: float = 0.035


@dataclass
class BargeCapacityResult:
    """Volume-bound capacity and the resulting full-load hydrostatics."""

    cargo_type: str
    phase: str                          # "liquid_gas" | "dry_bulk"
    cargo_density_t_per_m3: float

    # Headline outputs
    cargo_capacity_t: float             # volume-bound tonnage
    full_load_draft_m: float
    air_draft_m: float

    # Supporting
    cargo_volume_m3: float
    lightship_t: float
    displacement_t: float
    deadweight_t: float
    freeboard_m: float
    air_draft_top_above_keel_m: float
    overloaded: bool                    # True if volume load can't float within moulded depth

    # Gas design detail (None for bulk)
    tank_outer_diameter_m: Optional[float] = None
    n_tanks_wide: Optional[int] = None        # resolved arrangement (auto or forced)
    max_tank_od_m: Optional[float] = None     # the OD cap that resolved it
    n_tanks_total: Optional[int] = None
    side_clearance_m: Optional[float] = None
    bottom_clearance_m: Optional[float] = None

    # Bulk design detail (None for gas)
    hold_height_m: Optional[float] = None
    hold_top_width_m: Optional[float] = None
    hold_bottom_width_m: Optional[float] = None
    hold_section_area_m2: Optional[float] = None

    # Intact stability (bulk hopper only; gas uses hydrostatics.calculate_stability)
    gm_m: Optional[float] = None        # transverse metacentric height GM = KB + BM - KG

    # --- Arrangement (derived, not assumed) ---
    bow_void_length_m: Optional[float] = None    # forward non-cargo length (rake + end bhd)
    stern_void_length_m: Optional[float] = None  # aft non-cargo length (block + separation)
    cargo_zone_length_m: Optional[float] = None  # LOA - the two voids
    bow_rake_length_m: Optional[float] = None
    aft_arrangement: Optional[AftArrangementResult] = None
    separation: Optional[GasSeparationResult] = None

    # --- Cargo volume build-up (so the 95% is visible, not implied) ---
    # Gas: the INNER volume of the tanks, after insulation and steel shell are taken off
    # the outer diameter. Bulk: the geometric hold volume. `cargo_volume_m3` is this
    # figure multiplied by the fill ratio.
    containment_inner_volume_m3: Optional[float] = None
    fill_ratio_applied: Optional[float] = None
    insulation_thickness_mm: Optional[float] = None
    tank_wall_thickness_mm: Optional[float] = None
    tank_inner_diameter_m: Optional[float] = None

    # --- Light / ballast load conditions (bridge clearance governs here) ---
    light_draft_m: Optional[float] = None        # lightship-only equilibrium draft
    air_draft_light_m: Optional[float] = None    # GOVERNING air draft (empty leg)
    ballast_draft_m: Optional[float] = None      # draft with ballast_capacity_t aboard
    air_draft_ballast_m: Optional[float] = None  # air draft on the ballasted empty leg
    # Wheelhouse RAISED. The lifting wheelhouse is lowered to pass a bridge, so it is not
    # part of the transit air draft -- but it is the real height under way, so it is
    # reported rather than dropped.
    air_draft_navigating_light_m: Optional[float] = None
    navigating_top_above_keel_m: Optional[float] = None

    # Gas only: {"inputs": BargeInputs, "tanks": TankResult, "weights": WeightBreakdown} of the
    # converged arrangement, for gas_stability. None for bulk.
    gas_basis: Optional[dict] = None

    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


# Maximum gas tank outer diameter (m). DESIGN RULE, Niall 2026-09-17: cap tank OD at
# 12 m and go to two (or more) tanks across above that, rather than letting a single tank
# grow with the beam. This closes the `n_tanks_wide` gap AGENTS.md carried as TODO — a
# single tank abreast reached ~16 m OD at 20 m beam and ~30 m at 32.4 m, which is outside
# any built cryogenic barge tank and made every wide-beam gas number meaningless.
MAX_TANK_OD_M = 12.0


def tanks_wide_for_beam(beam_m: float, side_clearance_m: float,
                        tank_gap_transverse_m: float = 0.0,
                        max_od_m: float = MAX_TANK_OD_M) -> int:
    """Fewest tanks across the beam that keeps each tank's OD within ``max_od_m``.

    Inverts the arrangement geometry in ``tanks.calculate_tank_arrangement``:
        OD = (beam - 2*cs - (n-1)*gap) / n   <=   max_od
      => n >= (beam - 2*cs + gap) / (max_od + gap)
    Always at least 1, so a narrow hull is unaffected.
    """
    import math as _m
    usable = beam_m - 2.0 * side_clearance_m
    if usable <= 0:
        return 1
    n = _m.ceil((usable + tank_gap_transverse_m) / (max_od_m + tank_gap_transverse_m))
    return max(1, int(n))


def _gas_volumetric(inp: BargeCapacityInputs, bow_void_m: float, stern_void_m: float):
    """IGC/IGF protective-location clearances -> tank arrangement -> cargo volume.

    Resolves the volume <-> d(Vc) circular dependency by iterating. Tank OD is limited
    only by beam and side clearance (no depth cap, no air-draft cap).
    Returns (cargo_volume_m3, lightship_t, h_top_above_keel_m, detail dict).
    """
    base = BargeInputs(
        loa=inp.loa, beam=inp.beam, depth=inp.depth,
        max_draft=inp.depth, vertical_clearance=inp.depth * 10.0,
        vessel_type=inp.vessel_type, cargo_type=inp.cargo_type,
        # The cargo zone is bounded by the DERIVED voids, not by a fraction of LOA. Before
        # 2026-09-18 these were left at BargeInputs' 10%/15% defaults, so the aft tank head
        # sat against the accommodation with no gas-code separation at all.
        bow_non_tank_length=bow_void_m, stern_non_tank_length=stern_void_m,
        n_tanks_wide=inp.n_tanks_wide or 1, n_tanks_long=inp.n_tanks_long,
        tank_wall_thickness=inp.tank_wall_thickness, fill_ratio=inp.fill_ratio,
        dome_height=inp.dome_height, tank_support_height=inp.tank_support_height,
    )
    d_vc = 1.0
    bi = base
    tanks = None
    cs = cb = db = 0.0
    exact = inp.vessel_type == "IGC_2G_EXACT"
    # The engine measures clearance to the OUTER face of the insulation (OD includes it).
    # IGC measures to the steel, so under the exact rule the insulation sits inside d.
    ins_m = (getattr(base, "insulation_thickness", 0.0) or 0.0) / 1000.0
    for _ in range(40 if exact else 8):
        if exact:
            cs = max(d_vc - ins_m, 0.0)
            cb = max(min(inp.beam / 15.0, 2.0), d_vc) - ins_m
        else:
            req = compute_required_clearances(inp.vessel_type, inp.beam, d_vc)
            cs, cb = req.cs_required, req.cb_required
        if inp.side_clearance_override_m is not None:
            cs = inp.side_clearance_override_m
        db = max(0.0, cb - inp.tank_support_height)
        # AUTO tank arrangement: cs is only known inside this loop, and the OD cap is
        # expressed on cs, so n is resolved here rather than up front.
        n_wide = inp.n_tanks_wide
        if n_wide is None:
            n_wide = tanks_wide_for_beam(inp.beam, cs,
                                         getattr(base, "tank_gap_transverse", 0.0) or 0.0)
        bi = replace(base, side_clearance=cs, double_bottom_height=db,
                     n_tanks_wide=n_wide)
        tanks = calculate_tank_arrangement(bi)
        if exact:   # per-tank gross volume, linear bands: a continuous map, so it converges
            new_d_vc = d_vc_exact(tanks.total_tank_volume / max(tanks.n_tanks_total, 1))
        else:
            new_d_vc = distance_d_vc(tanks.total_tank_volume)
        if abs(new_d_vc - d_vc) < 1e-9:
            break
        d_vc = new_d_vc

    hull = HullGeometry(inp.loa, inp.beam, inp.depth, 0, 0, 0, 0)
    weights = calculate_weights(bi, hull, tanks)
    lightship = weights.lightship
    h_top = db + inp.tank_support_height + tanks.outer_diameter + inp.dome_height
    detail = dict(
        tank_outer_diameter_m=tanks.outer_diameter,
        n_tanks_wide=tanks.n_tanks_wide,
        max_tank_od_m=MAX_TANK_OD_M,
        n_tanks_total=tanks.n_tanks_total,
        side_clearance_m=cs,
        bottom_clearance_m=cb,
        # The volume build-up, reported so the reader can see what the tonnage is a
        # fraction OF. `tanks.total_tank_volume` is the INNER volume: the outer diameter
        # less twice the insulation and twice the steel wall. `cargo_volume` is that
        # inner volume x fill_ratio.
        containment_inner_volume_m3=tanks.total_tank_volume,
        fill_ratio_applied=inp.fill_ratio,
        insulation_thickness_mm=bi.insulation_thickness,
        tank_wall_thickness_mm=tanks.cylinder_wall_thickness,
        tank_inner_diameter_m=tanks.inner_diameter,
        # What the stability check needs: the converged arrangement and its weight split.
        gas_basis={"inputs": bi, "tanks": tanks, "weights": weights},
    )
    return tanks.cargo_volume, lightship, h_top, detail


def _bulk_volumetric(inp: BargeCapacityInputs, bow_void_m: float, stern_void_m: float):
    """Trapezoidal hopper hold geometry -> cargo volume + hopper structural weight.

    Returns (cargo_volume_m3, lightship_t, h_top_above_keel_m, detail dict).
    """
    d_db = inp.double_bottom_height_bulk
    s = inp.hopper_slope_h_per_v
    h_hold = (inp.depth - d_db) + inp.coaming_height
    w_top = inp.beam - 2.0 * inp.wing_void_width
    if inp.hold_type == "sloped_hopper":
        w_bot = max(1.0, w_top - 2.0 * s * h_hold)
    elif inp.hold_type in ("box", "container"):
        w_bot = w_top                       # vertical inner sides
    else:
        raise ValueError(f"unknown hold_type {inp.hold_type!r}")
    area = 0.5 * (w_top + w_bot) * h_hold
    l_cargo = max(0.0, inp.loa - bow_void_m - stern_void_m)
    hold_volume = area * l_cargo
    cargo_volume = hold_volume * inp.hold_fill_ratio

    # --- Hopper structural steel (plating-area method) ---
    t_ib = inp.inner_bottom_t_mm / 1000.0
    t_hop = inp.hopper_plate_t_mm / 1000.0
    t_bhd = inp.bulkhead_t_mm / 1000.0
    t_coam = inp.coaming_t_mm / 1000.0
    inner_bottom = l_cargo * inp.beam * t_ib
    hopper_slopes = 2.0 * (h_hold * math.sqrt(s * s + 1.0)) * l_cargo * t_hop
    wing_bulkheads = 2.0 * h_hold * l_cargo * t_bhd
    transverse_bhd = (inp.n_holds + 1) * area * t_bhd
    coaming = 2.0 * inp.coaming_height * l_cargo * t_coam
    steel_vol = inner_bottom + hopper_slopes + wing_bulkheads + transverse_bhd + coaming
    hopper_steel = steel_vol * inp.steel_density * inp.bulk_structure_factor

    hull_steel_td = inp.bulk_steel_rate_per_cbm * inp.loa * inp.beam * inp.depth
    base_steel = hull_steel_td + hopper_steel
    lightship = base_steel * (1.0 + inp.bulk_piping_factor + inp.bulk_outfitting_factor)
    if inp.hold_type != "sloped_hopper":
        if inp.lightship_k_t_per_m3 is None:
            raise ValueError(f"hold_type {inp.hold_type!r} needs lightship_k_t_per_m3 "
                             "(see calibration/factors.yaml)")
        lightship = inp.lightship_k_t_per_m3 * inp.loa * inp.beam * inp.depth

    h_top = inp.depth + inp.coaming_height
    detail = dict(
        hold_height_m=h_hold,
        hold_top_width_m=w_top,
        hold_bottom_width_m=w_bot,
        hold_section_area_m2=area,
        containment_inner_volume_m3=hold_volume,
        fill_ratio_applied=inp.hold_fill_ratio,
    )
    return cargo_volume, lightship, h_top, detail


def _bulk_gm(inp: BargeCapacityInputs, detail: dict, draft: float,
             lightship: float, cargo_t: float, hull: HullGeometry) -> float:
    """First-order transverse intact GM for the bulk hopper at full load.

    GM = KB + BM_t - KG.  Solid bulk has no liquid free surface, so GM_fluid = GM_solid
    (the separate cargo-shift / angle-of-repose hazard is flagged as a warning, not an FSC).
    KG combines lightship (assumed at 0.5 x moulded depth — first-order, flag) and cargo
    (centroid of the filled trapezoidal hold above the double bottom).
    """
    w_top = detail["hold_top_width_m"]
    w_bot = detail["hold_bottom_width_m"]
    h = detail["hold_height_m"]
    # trapezoid centroid above its base: h/3 * (2*top + bot)/(top + bot)
    zc = (h / 3.0) * (2.0 * w_top + w_bot) / (w_top + w_bot) if (w_top + w_bot) > 0 else h / 2.0
    kg_cargo = inp.double_bottom_height_bulk + zc
    kg_light = 0.5 * inp.depth
    total = lightship + cargo_t
    kg = (lightship * kg_light + cargo_t * kg_cargo) / total if total > 0 else kg_light
    return hull.KB(draft) + hull.BM_transverse(draft) - kg


def _arrangement(inp: BargeCapacityInputs, is_gas: bool):
    """Resolve the two non-cargo end lengths from the equipment and the code, not a %.

    Returns (bow_void_m, stern_void_m, bow_rake_m, aft_inputs, aft_pass1, separation).
    The aft block's LENGTH does not depend on the cargo, so it is resolved here; only the
    wheelhouse LIFT does, and that is a second pass once the cargo top is known.
    """
    # The MIX of 40 ft units differs by cargo (Niall, 2026-09-18): dry bulk carries a
    # second BATTERY, gas a second ACCOMMODATION unit. Three units abreast either way, so
    # the block LENGTH is the same for both vessels and only the beam requirement moves.
    aft_in = inp.aft or AftArrangementInputs(
        beam=inp.beam, depth=inp.depth,
        n_battery_units=1 if is_gas else 2,
        n_accom_units=2 if is_gas else 1)
    # Keep the block's beam/depth honest even if a caller passed an `aft` built elsewhere.
    aft_in = replace(aft_in, beam=inp.beam, depth=inp.depth)
    aft0 = compute_aft_arrangement(aft_in)
    block_len = aft0.length_m if inp.self_propelled else inp.pushed_stern_void_m

    rake = inp.bow_rake_length_m
    if rake is None:
        rake = 1.6 * inp.depth

    if is_gas:
        sep_in = inp.separation or GasSeparationInputs()
        sep = compute_gas_separation(sep_in)
        aft_sep, fwd_sep = sep.aft_separation_m, sep.fwd_separation_m
    else:
        sep = None
        aft_sep = fwd_sep = inp.bulk_end_bulkhead_m

    return (rake + fwd_sep, block_len + aft_sep, rake, aft_in, aft0, sep)


def compute(inp: BargeCapacityInputs) -> BargeCapacityResult:
    """Run the unified barge capacity chain (volume-bound)."""
    props = get_cargo(inp.cargo_type)
    density_t = props.density / 1000.0
    is_gas = props.phase != "dry_bulk"

    bow_void, stern_void, rake, aft_in, aft0, sep = _arrangement(inp, is_gas)
    cargo_zone = inp.loa - bow_void - stern_void

    geometry_error = None
    if props.phase == "dry_bulk":
        cargo_volume, lightship, h_top, detail = _bulk_volumetric(inp, bow_void, stern_void)
    else:
        try:
            cargo_volume, lightship, h_top, detail = _gas_volumetric(
                inp, bow_void, stern_void)
        except ValueError as exc:
            # A vessel too short for its own stern block, or too narrow for its tanks, is
            # INFEASIBLE -- not an exception. It has to come back as a failed check so a
            # grid sweep can print "0 t (infeasible)" for that cell and carry on. Raising
            # here took the whole sweep down and told the caller nothing about which cell.
            # (Bites short hulls now the stern block is a fixed ~19 m rather than 15% of
            # LOA: a 45 m vessel cannot hold two 40 ft units, three thrusters, a
            # wheelhouse AND a cargo area.)
            geometry_error = str(exc)
            cargo_volume, lightship, h_top = 0.0, 0.0, inp.depth
            detail = dict(tank_outer_diameter_m=None, n_tanks_wide=None,
                          max_tank_od_m=MAX_TANK_OD_M, n_tanks_total=None,
                          side_clearance_m=None, bottom_clearance_m=None,
                          containment_inner_volume_m3=0.0,
                          fill_ratio_applied=inp.fill_ratio,
                          insulation_thickness_mm=None, tank_wall_thickness_mm=None,
                          tank_inner_diameter_m=None)

    # --- Second pass on the aft block: the wheelhouse has to see over the cargo, and the
    # cargo top is only known now. Length is unchanged by the lift, so nothing upstream
    # moves -- this resolves heights only.
    cargo_top_above_keel = h_top
    aft = compute_aft_arrangement(replace(
        aft_in, sightline_obstruction_m=cargo_top_above_keel))

    # The tallest FIXED point of the vessel with the wheelhouse lowered for transit.
    # A PUSHED barge carries none of this -- the block is on the tug, and so is its air
    # draft. Folding it in here would charge the cargo hull for a deckhouse it does not
    # have, which is the same double-count the motor-vessel decision warns about.
    if inp.self_propelled:
        h_top = max(h_top, aft.block_top_lowered_m)
        h_top_navigating = max(h_top, aft.wheelhouse_top_raised_m)
    else:
        aft = None
        h_top_navigating = h_top

    cargo_capacity = cargo_volume * density_t

    # --- Full-load hydrostatics (volume-bound load) ---
    hull = HullGeometry(inp.loa, inp.beam, inp.depth, 0, 0, 0, 0)
    cb = inp.block_coefficient
    rho = inp.water_density
    total_weight = lightship + cargo_capacity

    # Box hull displacement plateaus at moulded depth; if the load needs more than that,
    # the design is overloaded (would float below the deck / sink).
    max_float_volume = hull.displaced_volume(inp.depth)
    required_volume = total_weight / (cb * rho)
    overloaded = required_volume > max_float_volume

    draft = find_equilibrium_draft(hull, total_weight, rho, inp.depth, cb)
    draft = min(draft, inp.depth)               # clamp to the gunwale (honest for overload)
    displacement = cb * hull.displaced_volume(draft) * rho
    freeboard = inp.depth - draft
    air_draft = h_top - draft

    # --- Light / ballast conditions ---------------------------------------------
    # An EMPTY barge floats high, so its air draft is the LARGEST and it is what a
    # bridge actually has to clear. Computed with the same box hull and block
    # coefficient as the laden case, so the two cannot diverge.
    light_draft = find_equilibrium_draft(hull, lightship, rho, inp.depth, cb)
    light_draft = min(light_draft, inp.depth)
    air_draft_light = h_top - light_draft

    ballast_draft = light_draft
    if inp.ballast_capacity_t > 0:
        ballast_draft = find_equilibrium_draft(
            hull, lightship + inp.ballast_capacity_t, rho, inp.depth, cb)
        ballast_draft = min(ballast_draft, inp.depth)
    air_draft_ballast = h_top - ballast_draft
    air_draft_navigating_light = h_top_navigating - light_draft

    checks = [
        Check("feasible_geometry", cargo_volume > 0,
              geometry_error or "cargo volume must be positive (tank/hold fits)"),
        Check("not_overloaded", not overloaded,
              "volume-bound load must float within the moulded depth"),
        Check("freeboard_ok", freeboard >= inp.required_freeboard,
              f"freeboard {freeboard:.2f} m >= required {inp.required_freeboard} m"),
        Check("cargo_zone_positive", cargo_zone > 0,
              f"cargo zone {cargo_zone:.2f} m = LOA {inp.loa:.1f} - bow void "
              f"{bow_void:.2f} m - stern void {stern_void:.2f} m"),
    ]
    # Roll up the arrangement and gas-code checks so one `ok` covers the whole vessel.
    if aft is not None:
        checks.extend(aft.checks)
    if sep is not None:
        # Re-run with the as-designed clearances so the type-G floors are checked against
        # real numbers rather than zeros. Same pure function, same inputs plus two.
        sep = compute_gas_separation(replace(
            inp.separation or GasSeparationInputs(),
            side_clearance_m=detail.get("side_clearance_m") or 0.0,
            double_bottom_m=detail.get("bottom_clearance_m") or 0.0))
        checks.extend(sep.checks)
    # Bridge clearance is gated on the LIGHT (or ballasted-light) condition, never on
    # the laden one. The laden figure is the favourable case and gating on it passes
    # designs that cannot make the empty return leg.
    if inp.air_draft_limit_m is not None:
        governing = air_draft_ballast if inp.ballast_capacity_t > 0 else air_draft_light
        label = "ballasted light" if inp.ballast_capacity_t > 0 else "light"
        checks.append(Check(
            "air_draft_within_limit", governing <= inp.air_draft_limit_m,
            f"{label} air draft {governing:.2f} m <= limit {inp.air_draft_limit_m:.2f} m "
            f"(laden is {air_draft:.2f} m and is NOT the governing case)"))
    warnings = ((list(aft.warnings) if aft is not None else
                 ["PUSHED barge: crew, battery and propulsion are on the tug and are NOT "
                  "in this hull's lightship, capacity or air draft. The tug is a separate "
                  "vessel and must be costed and air-draft-gated separately."])
                + (list(sep.warnings) if sep is not None else []))
    gm = None
    if props.phase == "dry_bulk" and draft > 0 and not overloaded:
        gm = _bulk_gm(inp, detail, draft, lightship, cargo_capacity, hull)
        checks.append(Check("gm_positive", gm >= 0.15,
                            f"hopper intact GM {gm:.2f} m >= 0.15 m (first-order; KG_light @0.5D)",
                            severity="warning"))
        warnings.append("Bulk GM is first-order (assumed lightship KG); cargo-shift/angle-of-repose "
                        "not modelled — confirm with a full intact-stability booklet.")

    return BargeCapacityResult(
        cargo_type=props.name,
        phase=props.phase,
        cargo_density_t_per_m3=density_t,
        cargo_capacity_t=cargo_capacity,
        full_load_draft_m=draft,
        air_draft_m=air_draft,
        cargo_volume_m3=cargo_volume,
        lightship_t=lightship,
        displacement_t=displacement,
        deadweight_t=displacement - lightship,
        freeboard_m=freeboard,
        air_draft_top_above_keel_m=h_top,
        bow_void_length_m=bow_void,
        stern_void_length_m=stern_void,
        cargo_zone_length_m=cargo_zone,
        bow_rake_length_m=rake,
        aft_arrangement=aft,
        separation=sep,
        light_draft_m=light_draft,
        air_draft_light_m=air_draft_light,
        air_draft_navigating_light_m=air_draft_navigating_light,
        navigating_top_above_keel_m=h_top_navigating,
        ballast_draft_m=ballast_draft,
        air_draft_ballast_m=air_draft_ballast,
        overloaded=overloaded,
        gm_m=gm,
        checks=checks,
        warnings=warnings,
        **detail,
    )
