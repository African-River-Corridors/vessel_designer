"""Main barge design calculator orchestrating all modules."""

import math
from dataclasses import replace

from .cargo import get_cargo
from .hull import HullGeometry
from .hydrostatics import calculate_stability, calculate_trim, find_equilibrium_draft
from .models import BargeInputs, BargeResults
from .protective_location import (
    check_protective_location,
    compute_required_clearances,
    distance_d_vc,
)
from .tanks import calculate_tank_arrangement
from .weights import calculate_weights


class BargeCalculator:
    """ATB LNG/LPG barge design calculator.

    Usage:
        inputs = BargeInputs(loa=135, beam=26, depth=6.5, max_draft=6.0,
                             vertical_clearance=7.0, ...)
        calc = BargeCalculator(inputs)
        results = calc.calculate()
    """

    def __init__(self, inputs: BargeInputs):
        self.inputs = inputs

    def _optimize_clearances(self, inputs: BargeInputs):
        """Auto-derive side_clearance and double_bottom_height from protective location rules.

        Iterates to resolve the circular dependency between tank volume and d(Vc).
        Returns (optimized_inputs, binding_constraints).
        """
        binding = []
        needs_sc = inputs.side_clearance is None
        needs_db = inputs.double_bottom_height is None

        if not needs_sc and not needs_db:
            # Both explicitly set — nothing to optimize
            return inputs, binding

        beam = inputs.beam
        n_wide = inputs.n_tanks_wide

        # --- Iterative resolution (volume ↔ d_vc circular dependency) ---
        # Seed with conservative d_vc = 2.0 (large volume bracket)
        d_vc = 2.0
        eff_sc = inputs.side_clearance if not needs_sc else 0.0
        eff_db = inputs.double_bottom_height if not needs_db else 0.0

        for _ in range(3):
            req = compute_required_clearances(inputs.vessel_type, beam, d_vc)

            if needs_sc:
                eff_sc = req.cs_required
            if needs_db:
                eff_db = max(0.0, req.cb_required - inputs.tank_support_height)

            # Estimate tank diameter from beam geometry
            available_beam = beam - 2.0 * eff_sc
            tank_width_total = available_beam - (n_wide - 1) * inputs.tank_gap_transverse
            est_diameter = tank_width_total / n_wide
            if est_diameter <= 0:
                break  # can't fit tanks; downstream will raise

            # Estimate volume to determine d_vc bracket
            if inputs.tank_wall_thickness is not None:
                wall_m = inputs.tank_wall_thickness / 1000.0
            else:
                from .pressure_vessel import calculate_wall_thicknesses
                t_cyl, _ = calculate_wall_thicknesses(
                    outer_diameter_m=est_diameter,
                    design_pressure_mpa=inputs.design_pressure,
                    material_key=inputs.tank_material,
                    head_type=inputs.tank_head_type,
                    weld_efficiency=inputs.weld_efficiency,
                )
                wall_m = t_cyl / 1000.0
            inner_r = (est_diameter - 2.0 * wall_m) / 2.0
            if inner_r <= 0:
                break

            if inputs.tank_head_type == "hemisphere":
                head_len = est_diameter / 2.0
                vol_heads = 2.0 * (2.0 / 3.0) * math.pi * inner_r**3
            else:
                head_len = est_diameter / 4.0
                vol_heads = 2.0 * (1.0 / 3.0) * math.pi * inner_r**3

            avail_len = inputs.loa - inputs.bow_non_tank_length - inputs.stern_non_tank_length
            n_long = inputs.n_tanks_long
            tank_len = (avail_len - (n_long - 1) * inputs.tank_gap_longitudinal) / n_long
            cyl_len = tank_len - 2.0 * head_len
            if cyl_len <= 0:
                break

            vol_per_tank = math.pi * inner_r**2 * cyl_len + vol_heads
            total_vol = n_wide * n_long * vol_per_tank

            new_d_vc = distance_d_vc(total_vol)
            if new_d_vc == d_vc:
                break  # converged
            d_vc = new_d_vc

        # --- Air draft cap ---
        # max height above keel for tank top = vertical_clearance + max_draft
        max_tank_top = inputs.vertical_clearance + inputs.max_draft
        max_diameter_from_air = max_tank_top - eff_db - inputs.tank_support_height

        beam_diameter = est_diameter if est_diameter > 0 else 0.0

        if needs_sc and max_diameter_from_air < beam_diameter and max_diameter_from_air > 0:
            # Air draft is binding — increase side clearance to cap diameter
            capped_diameter = max_diameter_from_air
            needed_total_width = capped_diameter * n_wide + (n_wide - 1) * inputs.tank_gap_transverse
            eff_sc = (beam - needed_total_width) / 2.0
            eff_sc = max(eff_sc, req.cs_required)  # never go below code minimum
            binding.append("Air draft limits tank diameter")

        # Track which constraints are binding
        if needs_sc:
            binding.append(f"Side clearance Cs auto-set to {eff_sc:.2f} m ({inputs.vessel_type})")
        if needs_db:
            binding.append(f"Double bottom auto-set to {eff_db:.2f} m ({inputs.vessel_type})")

        optimized = replace(inputs, side_clearance=eff_sc, double_bottom_height=eff_db)
        return optimized, binding

    def calculate(self) -> BargeResults:
        """Run the full design calculation and return results."""
        # --- 0. Auto-optimize clearances ---
        inputs, binding_constraints = self._optimize_clearances(self.inputs)
        warnings = []

        # --- 1. Hull geometry ---
        hull = HullGeometry(
            loa=inputs.loa,
            beam=inputs.beam,
            depth=inputs.depth,
            bow_rake_length=inputs.bow_rake_length,
            bow_rake_rise=inputs.bow_rake_rise,
            stern_rake_length=inputs.stern_rake_length,
            stern_rake_rise=inputs.stern_rake_rise,
        )

        # --- 2. Tank arrangement ---
        tanks = calculate_tank_arrangement(inputs)

        # --- 3. Air draft check ---
        # Tank top above keel = double_bottom + support + outer_diameter
        # Air draft = tank_top_above_keel - draft (height above waterline)
        # We don't know draft yet, so check against depth first
        # After draft is solved, we re-check
        tank_top = tanks.tank_top_above_keel

        # --- 4. Cargo ---
        if inputs.cargo_density_override is not None:
            cargo_density_t = inputs.cargo_density_override / 1000.0  # kg/m^3 to t/m^3
            cargo_type_name = f"Custom ({inputs.cargo_density_override:.0f} kg/m3)"
        else:
            cargo_props = get_cargo(inputs.cargo_type)
            cargo_density_t = cargo_props.density / 1000.0  # kg/m^3 to t/m^3
            cargo_type_name = cargo_props.name
        cargo_mass = tanks.cargo_volume * cargo_density_t

        # --- 5. Weights ---
        weight_breakdown = calculate_weights(inputs, hull, tanks)

        # --- 6. Total weight and equilibrium draft ---
        total_weight = weight_breakdown.lightship + cargo_mass
        draft = find_equilibrium_draft(
            hull=hull,
            total_weight=total_weight,
            water_density=inputs.water_density,
            max_draft=inputs.depth,  # Can't draft more than depth
            block_coefficient=inputs.block_coefficient,
        )

        # Check draft against max_draft
        if draft > inputs.max_draft:
            warnings.append(
                f"Draft {draft:.3f}m exceeds max draft {inputs.max_draft}m. "
                f"Vessel is overloaded for the design constraint."
            )

        # --- 7. Displacement and deadweight ---
        displacement = hull.displaced_volume(draft) * inputs.water_density
        deadweight = displacement - weight_breakdown.lightship

        # --- 8. Freeboard ---
        # Freeboard measured from waterline to wing plate level (effective moulded depth)
        freeboard = weight_breakdown.moulded_depth - draft
        min_freeboard_ok = freeboard >= 0.3

        if not min_freeboard_ok:
            warnings.append(
                f"Freeboard {freeboard:.3f}m is below minimum 0.3m."
            )

        # --- 9. Air draft (re-check with actual draft) ---
        # Highest point is dome top (if present), otherwise tank top
        dome_top = tank_top + getattr(inputs, 'dome_height', 0.0)
        air_draft = dome_top - draft
        air_draft_ok = air_draft <= inputs.vertical_clearance
        # Unladen (lightship) air draft — the barge rides higher empty, so this is the
        # bridge-critical figure. Equilibrium draft carrying lightship only.
        unladen_draft = find_equilibrium_draft(
            hull=hull, total_weight=weight_breakdown.lightship,
            water_density=inputs.water_density, max_draft=inputs.depth,
            block_coefficient=inputs.block_coefficient)
        air_draft_unladen = dome_top - unladen_draft

        if not air_draft_ok:
            warnings.append(
                f"Air draft {air_draft:.2f}m exceeds vertical clearance "
                f"{inputs.vertical_clearance}m."
            )

        # --- 10. Stability ---
        stability = calculate_stability(
            hull=hull,
            inputs=inputs,
            tanks=tanks,
            weights=weight_breakdown,
            cargo_mass=cargo_mass,
            cargo_density_t=cargo_density_t,
            draft=draft,
        )

        stability_ok = stability.GM_fluid > 0.15
        if not stability_ok:
            warnings.append(
                f"GM_fluid {stability.GM_fluid:.3f}m is below minimum 0.15m. "
                f"Vessel may be unstable."
            )

        # --- 11. Trim ---
        trim_result = calculate_trim(
            hull=hull,
            inputs=inputs,
            tanks=tanks,
            weights=weight_breakdown,
            cargo_mass=cargo_mass,
            draft=draft,
        )

        # --- 12. Total depth required ---
        total_depth_required = draft + inputs.underkeel_clearance

        # --- 13. Protective location (IGF/IGC Code) ---
        prot_loc = check_protective_location(
            vessel_type_str=inputs.vessel_type,
            beam=inputs.beam,
            total_tank_volume=tanks.total_tank_volume,
            side_clearance=inputs.side_clearance,
            double_bottom_height=inputs.double_bottom_height,
            tank_support_height=inputs.tank_support_height,
        )
        if not prot_loc.cs_ok:
            warnings.append(
                f"Side clearance {prot_loc.cs_actual:.2f}m is below "
                f"{inputs.vessel_type} required {prot_loc.cs_required:.2f}m."
            )
        if not prot_loc.cb_ok:
            warnings.append(
                f"Bottom clearance {prot_loc.cb_actual:.2f}m is below "
                f"required {prot_loc.cb_required:.2f}m."
            )

        # Check cargo capacity vs deadweight
        if cargo_mass > deadweight:
            warnings.append(
                f"Cargo mass {cargo_mass:.1f}t exceeds deadweight {deadweight:.1f}t. "
                f"Reduce cargo or increase vessel size."
            )

        return BargeResults(
            inputs=inputs,
            tanks=tanks,
            cargo_type=cargo_type_name,
            cargo_density=cargo_density_t,
            cargo_mass=cargo_mass,
            weights=weight_breakdown,
            displacement=displacement,
            deadweight=deadweight,
            draft=draft,
            freeboard=freeboard,
            min_freeboard_ok=min_freeboard_ok,
            air_draft=air_draft,
            air_draft_unladen=air_draft_unladen,
            air_draft_ok=air_draft_ok,
            stability=stability,
            stability_ok=stability_ok,
            trim=trim_result,
            total_depth_required=total_depth_required,
            protective_location=prot_loc,
            binding_constraints=binding_constraints,
            warnings=warnings,
        )


def print_results(results: BargeResults) -> None:
    """Print a formatted summary of barge design results."""
    r = results
    i = r.inputs

    print("=" * 70)
    print("  ATB LNG/LPG BARGE DESIGN CALCULATOR - RESULTS")
    print("=" * 70)

    print(f"\n--- PRINCIPAL DIMENSIONS ---")
    print(f"  LOA:                  {i.loa:.1f} m")
    print(f"  Beam:                 {i.beam:.1f} m")
    print(f"  Depth:                {i.depth:.2f} m")
    print(f"  Max draft:            {i.max_draft:.2f} m")
    print(f"  Vertical clearance:   {i.vertical_clearance:.1f} m")
    print(f"  Bow non-tank zone:    {i.bow_non_tank_length:.1f} m")
    print(f"  Stern non-tank zone:  {i.stern_non_tank_length:.1f} m")
    if i.bow_rake_length > 0:
        print(f"  Bow rake:             {i.bow_rake_length:.1f} m long, {i.bow_rake_rise:.1f} m rise")
    if i.stern_rake_length > 0:
        print(f"  Stern rake:           {i.stern_rake_length:.1f} m long, {i.stern_rake_rise:.1f} m rise")

    print(f"\n--- TANK ARRANGEMENT ---")
    t = r.tanks
    print(f"  Layout:               {t.n_tanks_wide} wide x {t.n_tanks_long} long = {t.n_tanks_total} tanks")
    print(f"  Outer diameter:       {t.outer_diameter:.3f} m")
    print(f"  Inner diameter:       {t.inner_diameter:.3f} m")
    print(f"  Overall tank length:  {t.overall_tank_length:.2f} m")
    print(f"  Cylinder length:      {t.cylinder_length:.2f} m")
    print(f"  Head type:            {i.tank_head_type}")
    print(f"  Head length:          {t.head_length:.3f} m")
    print(f"  Wall thickness (cyl): {t.cylinder_wall_thickness:.1f} mm")
    print(f"  Wall thickness (head):{t.head_wall_thickness:.1f} mm")
    if t.tank_material:
        print(f"  Tank material:        {t.tank_material}")
    print(f"  Design pressure:      {t.design_pressure:.2f} MPa ({t.design_pressure*10:.1f} barg)")
    print(f"  Volume per tank:      {t.volume_per_tank:.1f} m3")
    print(f"    Cylinder:           {t.volume_cylinder:.1f} m3")
    print(f"    Heads:              {t.volume_heads:.1f} m3")
    print(f"  Total tank volume:    {t.total_tank_volume:.1f} m3")
    print(f"  Cargo volume ({i.fill_ratio*100:.0f}%):   {t.cargo_volume:.1f} m3")

    print(f"\n--- CARGO ---")
    print(f"  Cargo type:           {r.cargo_type}")
    print(f"  Cargo density:        {r.cargo_density:.3f} t/m3 ({r.cargo_density*1000:.0f} kg/m3)")
    print(f"  Cargo mass:           {r.cargo_mass:.1f} tonnes")

    print(f"\n--- WEIGHT BREAKDOWN ---")
    w = r.weights
    print(f"  Hull bottom plating:  {w.hull_bottom_plating:.1f} t")
    print(f"  Hull side plating:    {w.hull_side_plating:.1f} t")
    print(f"  Hull deck plating:    {w.hull_deck_plating:.1f} t")
    print(f"  Hull rake plating:    {w.hull_rake_plating:.1f} t")
    print(f"  Internal structure:   {w.hull_internal_structure:.1f} t")
    print(f"  Hull steel total:     {w.hull_steel_total:.1f} t")
    print(f"  Tank shells:          {w.tank_shells:.1f} t")
    print(f"  Tank internals/suppt: {w.tank_internals_supports:.1f} t")
    print(f"  Tank total:           {w.tank_total:.1f} t")
    print(f"  Insulation:           {w.insulation:.1f} t")
    print(f"  Piping & machinery:   {w.piping_machinery:.1f} t")
    print(f"  Outfitting:           {w.outfitting:.1f} t")
    print(f"  -------------------------")
    print(f"  LIGHTSHIP:            {w.lightship:.1f} t")

    print(f"\n--- HYDROSTATICS ---")
    print(f"  Total loaded weight:  {w.lightship + r.cargo_mass:.1f} t")
    print(f"  Displacement:         {r.displacement:.1f} t")
    print(f"  Deadweight:           {r.deadweight:.1f} t")
    print(f"  Equilibrium draft:    {r.draft:.3f} m")
    print(f"  Freeboard:            {r.freeboard:.3f} m  {'OK' if r.min_freeboard_ok else 'LOW!'}")

    print(f"\n--- AIR DRAFT ---")
    print(f"  Tank top above keel:  {t.tank_top_above_keel:.2f} m")
    print(f"  Air draft:            {r.air_draft:.2f} m  {'OK' if r.air_draft_ok else 'EXCEEDS!'}")
    print(f"  Clearance limit:      {i.vertical_clearance:.1f} m")

    if r.protective_location:
        pl = r.protective_location
        print(f"\n--- PROTECTIVE LOCATION ({pl.vessel_type}) ---")
        print(f"  d(Vc) [{pl.total_tank_volume:.0f} m3]: {pl.d_vc:.1f} m")
        print(f"  Side Cs required:     {pl.cs_required:.2f} m")
        print(f"  Side Cs actual:       {pl.cs_actual:.2f} m  {'OK' if pl.cs_ok else 'FAIL!'}")
        print(f"  Bottom Cb required:   {pl.cb_required:.2f} m")
        print(f"  Bottom Cb actual:     {pl.cb_actual:.2f} m  {'OK' if pl.cb_ok else 'FAIL!'}")

    print(f"\n--- STABILITY ---")
    s = r.stability
    print(f"  KB:                   {s.KB:.3f} m")
    print(f"  BM (transverse):      {s.BM_transverse:.3f} m")
    print(f"  KG:                   {s.KG:.3f} m")
    print(f"  GM (solid):           {s.GM_solid:.3f} m")
    print(f"  Free surface corr:    {s.free_surface_correction:.3f} m")
    print(f"  GM (fluid):           {s.GM_fluid:.3f} m  {'OK' if r.stability_ok else 'UNSTABLE!'}")

    print(f"\n--- TRIM ---")
    tr = r.trim
    print(f"  LCG (from AP):        {tr.LCG:.2f} m")
    print(f"  LCB (from AP):        {tr.LCB:.2f} m")
    print(f"  Trim:                 {tr.trim:.3f} m  ({'bow down' if tr.trim > 0 else 'stern down' if tr.trim < 0 else 'even keel'})")
    print(f"  Draft aft:            {tr.draft_aft:.3f} m")
    print(f"  Draft fwd:            {tr.draft_fwd:.3f} m")

    print(f"\n--- CHANNEL DEPTH ---")
    print(f"  Total depth required: {r.total_depth_required:.2f} m (draft + {i.underkeel_clearance}m UKC)")

    if r.binding_constraints:
        print(f"\n--- BINDING CONSTRAINTS ---")
        for bc in r.binding_constraints:
            print(f"  * {bc}")

    if r.warnings:
        print(f"\n--- WARNINGS ---")
        for w_msg in r.warnings:
            print(f"  * {w_msg}")

    print("=" * 70)
