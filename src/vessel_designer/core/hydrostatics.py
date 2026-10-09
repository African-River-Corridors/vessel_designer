"""Hydrostatic calculations: displacement, draft, stability, and trim."""

import math

from .hull import HullGeometry
from .models import (
    BargeInputs,
    StabilityResult,
    TankResult,
    TrimResult,
    WeightBreakdown,
)
from .tanks import free_surface_moment_cylindrical


def find_equilibrium_draft(
    hull: HullGeometry,
    total_weight: float,
    water_density: float,
    max_draft: float,
    block_coefficient: float = 1.0,
    tolerance: float = 0.001,
) -> float:
    """Find the draft at which displacement equals total weight.

    Uses bisection method since displaced_volume is monotonically increasing
    with draft.

    The block coefficient Cb accounts for the difference between the
    moulded hull volume and the actual displacement volume:
        Effective displacement = Cb × hull_volume × water_density

    Args:
        hull: Hull geometry object
        total_weight: Total loaded weight (tonnes)
        water_density: Water density (t/m^3)
        max_draft: Upper bound for search (m)
        block_coefficient: Cb, ratio of actual to moulded displacement (0-1)
        tolerance: Convergence tolerance (m)

    Returns:
        Equilibrium draft (m)
    """
    required_volume = total_weight / (water_density * block_coefficient)

    lo = 0.0
    hi = max_draft * 1.5  # Allow some margin to detect overload

    for _ in range(100):
        mid = (lo + hi) / 2.0
        vol = hull.displaced_volume(mid)
        if abs(vol - required_volume) < tolerance * hull.beam:
            return mid
        if vol < required_volume:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2.0


def calculate_stability(
    hull: HullGeometry,
    inputs: BargeInputs,
    tanks: TankResult,
    weights: WeightBreakdown,
    cargo_mass: float,
    cargo_density_t: float,
    draft: float,
) -> StabilityResult:
    """Calculate intact stability (GM) at the equilibrium draft.

    Args:
        hull: Hull geometry
        inputs: Barge inputs
        tanks: Tank results
        weights: Weight breakdown
        cargo_mass: Cargo mass (tonnes)
        cargo_density_t: Cargo density (t/m^3)
        draft: Equilibrium draft (m)

    Returns:
        StabilityResult with KB, BM, KG, GM values.
    """
    cb = getattr(inputs, 'block_coefficient', 1.0)
    displacement = hull.displaced_volume(draft) * inputs.water_density * cb

    # --- KB ---
    kb = hull.KB(draft)

    # --- BM ---
    bm_t = hull.BM_transverse(draft)
    bm_l = hull.BM_longitudinal(draft)

    # --- KG (center of gravity above keel) ---
    # Weighted average of all component centers of gravity

    # Hull steel: approximate CG at depth/2
    kg_hull = inputs.depth / 2.0
    w_hull = weights.hull_steel_total

    # Tanks + insulation: CG at center of tank
    kg_tanks = (inputs.double_bottom_height
                + inputs.tank_support_height
                + tanks.outer_diameter / 2.0)
    w_tanks = weights.tank_shells + weights.insulation

    # Cargo: CG approximately at tank center (slightly lower for partial fill,
    # but close enough for 95% fill)
    kg_cargo = kg_tanks
    w_cargo = cargo_mass

    # Piping: approximate CG at deck level
    kg_piping = inputs.depth
    w_piping = weights.piping_machinery

    # Outfitting: approximate CG at 0.75 * depth
    kg_outfitting = 0.75 * inputs.depth
    w_outfitting = weights.outfitting

    # Stores (diesel, fresh water): approximate CG in double bottom / low in hull
    kg_stores = inputs.double_bottom_height / 2.0 if inputs.double_bottom_height else inputs.depth * 0.25
    w_stores = weights.stores

    total_w = w_hull + w_tanks + w_cargo + w_piping + w_outfitting + w_stores
    if total_w > 0:
        kg = (w_hull * kg_hull
              + w_tanks * kg_tanks
              + w_cargo * kg_cargo
              + w_piping * kg_piping
              + w_outfitting * kg_outfitting
              + w_stores * kg_stores) / total_w
    else:
        kg = inputs.depth / 2.0

    # --- GM (solid) ---
    gm_solid = kb + bm_t - kg

    # --- Free surface correction ---
    # Sum free surface moments for all tanks
    total_fs_moment = 0.0
    for _ in range(tanks.n_tanks_total):
        fs_moment = free_surface_moment_cylindrical(
            inner_radius=tanks.inner_diameter / 2.0,
            cylinder_length=tanks.cylinder_length,
            fill_ratio=inputs.fill_ratio,
            cargo_density=cargo_density_t,
        )
        total_fs_moment += fs_moment

    if displacement > 0:
        fs_correction = total_fs_moment / displacement
    else:
        fs_correction = 0.0

    gm_fluid = gm_solid - fs_correction

    return StabilityResult(
        KB=kb,
        BM_transverse=bm_t,
        KG=kg,
        GM_solid=gm_solid,
        free_surface_correction=fs_correction,
        GM_fluid=gm_fluid,
        BM_longitudinal=bm_l,
    )


def calculate_trim(
    hull: HullGeometry,
    inputs: BargeInputs,
    tanks: TankResult,
    weights: WeightBreakdown,
    cargo_mass: float,
    draft: float,
) -> TrimResult:
    """Calculate longitudinal trim.

    Convention: x measured from stern (AP). x=0 at stern, x=LOA at bow.
    Positive trim = bow deeper than stern.

    Args:
        hull: Hull geometry
        inputs: Barge inputs
        tanks: Tank results
        weights: Weight breakdown
        cargo_mass: Cargo mass (tonnes)
        draft: Equilibrium draft (m)

    Returns:
        TrimResult with LCG, LCB, trim, and drafts at bow/stern.
    """
    cb = getattr(inputs, 'block_coefficient', 1.0)
    displacement = hull.displaced_volume(draft) * inputs.water_density * cb

    # --- LCB (longitudinal center of buoyancy from AP) ---
    lcb = hull.LCB(draft)

    # --- LCG (longitudinal center of gravity from AP) ---
    # Hull steel: CG approximately at midship
    lcg_hull = inputs.loa / 2.0
    w_hull = weights.hull_steel_total

    # Tanks + insulation + cargo: centered in the tank zone
    # Tank zone: from stern_non_tank_length to (LOA - bow_non_tank_length)
    tank_zone_start = inputs.stern_non_tank_length  # from stern
    tank_zone_end = inputs.loa - inputs.bow_non_tank_length
    tank_zone_center = (tank_zone_start + tank_zone_end) / 2.0

    w_tanks = weights.tank_shells + weights.insulation
    w_cargo = cargo_mass

    # Piping: distributed, approximate at midship
    lcg_piping = inputs.loa / 2.0
    w_piping = weights.piping_machinery

    # Outfitting: approximate at stern (accommodation/machinery in aft zone)
    lcg_outfitting = inputs.stern_non_tank_length / 2.0
    w_outfitting = weights.outfitting

    # Stores (diesel, fresh water): in aft machinery zone
    lcg_stores = inputs.stern_non_tank_length / 2.0
    w_stores = weights.stores

    total_w = w_hull + w_tanks + w_cargo + w_piping + w_outfitting + w_stores
    if total_w > 0:
        lcg = (w_hull * lcg_hull
               + w_tanks * tank_zone_center
               + w_cargo * tank_zone_center
               + w_piping * lcg_piping
               + w_outfitting * lcg_outfitting
               + w_stores * lcg_stores) / total_w
    else:
        lcg = inputs.loa / 2.0

    # --- Trim ---
    bm_l = hull.BM_longitudinal(draft)

    if bm_l > 0 and displacement > 0:
        # Trim moment = displacement * (LCG - LCB)
        # Trim = moment / (displacement * BM_L / L) = (LCG - LCB) * L / BM_L
        # Actually: trim (in metres) = (LCG - LCB) * displacement / (I_L * water_density / L)
        # Simplified: trim = (LCG - LCB) * L / BM_L
        l_wp = hull.waterplane_length(draft)
        trim = (lcg - lcb) * l_wp / bm_l
    else:
        trim = 0.0

    # Positive trim = bow deeper
    draft_aft = draft - trim / 2.0
    draft_fwd = draft + trim / 2.0

    return TrimResult(
        LCG=lcg,
        LCB=lcb,
        trim=trim,
        draft_aft=draft_aft,
        draft_fwd=draft_fwd,
    )
