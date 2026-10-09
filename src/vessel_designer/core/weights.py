"""Component weight breakdown for ATB barge."""

import math

from .hull import HullGeometry
from .models import BargeInputs, TankResult, WeightBreakdown


def calculate_weights(
    inputs: BargeInputs,
    hull: HullGeometry,
    tanks: TankResult,
) -> WeightBreakdown:
    """Calculate component weight breakdown.

    Hull steel estimated from plating areas and thicknesses, plus a
    structure factor for internal framing (floors, frames, longitudinals,
    bulkheads).

    Args:
        inputs: Barge design inputs
        hull: Hull geometry object
        tanks: Tank arrangement results

    Returns:
        WeightBreakdown with all component weights in tonnes.
    """
    steel_density = inputs.hull_steel_density  # t/m^3

    # Convert plate thicknesses from mm to m
    t_bottom = inputs.bottom_plate_thickness / 1000.0
    t_side = inputs.side_plate_thickness / 1000.0
    t_deck = inputs.deck_plate_thickness / 1000.0

    # --- Hull plating weights ---
    w_bottom = hull.bottom_area() * t_bottom * steel_density
    w_side = hull.side_area() * t_side * steel_density
    w_deck = hull.deck_area() * t_deck * steel_density

    # Rake plating - use average of bottom and side thickness
    t_rake = (t_bottom + t_side) / 2.0
    w_rake = (hull.bow_rake_area() + hull.stern_rake_area()) * t_rake * steel_density

    # Plating subtotal
    w_plating = w_bottom + w_side + w_deck + w_rake

    # Internal structure (frames, floors, longitudinals, bulkheads)
    w_structure = w_plating * (inputs.structure_factor - 1.0)

    # Total hull steel
    w_hull_total = w_plating + w_structure

    # --- Tank weights (from tank calculation) ---
    w_tank_shells = tanks.tank_shell_weight
    # Internal stiffeners, ring frames, support saddles/stools
    w_tank_internals = w_tank_shells * (inputs.tank_structure_factor - 1.0)
    w_tank_total = w_tank_shells + w_tank_internals
    w_insulation = tanks.insulation_weight

    # --- Wing plate (horizontal steel shelf at wing tank top level) ---
    # Full beam × full LOA, minus cutouts where tanks pass through in tank zone
    w_wing_plate = 0.0
    if inputs.wing_tank_width > 0 and inputs.wing_tank_height_ratio < 1.0:
        db = inputs.double_bottom_height if inputs.double_bottom_height is not None else 0.0
        tank_od = tanks.outer_diameter
        tank_r = tank_od / 2.0
        cargo_tank_bottom = db + inputs.tank_support_height
        wing_tank_top = cargo_tank_bottom + inputs.wing_tank_height_ratio * tank_od
        tank_center_y = cargo_tank_bottom + tank_r

        # Chord width of tank at plate elevation (cutout in tank zone only)
        dy = wing_tank_top - tank_center_y
        if abs(dy) < tank_r:
            chord_width = 2.0 * math.sqrt(tank_r**2 - dy**2)
        else:
            chord_width = 0.0

        tank_zone_length = inputs.loa - inputs.bow_non_tank_length - inputs.stern_non_tank_length
        non_tank_length = inputs.loa - tank_zone_length  # bow + stern zones
        t_deck_plate = inputs.deck_plate_thickness / 1000.0

        # In tank zone: beam minus chord cutouts per tank abreast
        net_plate_width_tz = inputs.beam - inputs.n_tanks_wide * chord_width
        w_plate_tank_zone = net_plate_width_tz * tank_zone_length * t_deck_plate * steel_density

        # In non-tank zones: full beam (no tank cutouts)
        w_plate_non_tank = inputs.beam * non_tank_length * t_deck_plate * steel_density

        w_wing_plate = w_plate_tank_zone + w_plate_non_tank

        # Side plating extension from deck to wing plate level (full LOA)
        # This is additional side plating above the main hull depth
        side_extension_height = wing_tank_top - inputs.depth
        if side_extension_height > 0:
            # Two sides × extension height × LOA × side plate thickness
            w_side_extension = 2.0 * side_extension_height * inputs.loa * t_side * steel_density
            w_wing_plate += w_side_extension

    # --- Weather shield (enclosure above wing plate, around exposed tank) ---
    # Top plate at cargo tank top + two side walls from wing plate to top
    w_weather_shield = 0.0
    if inputs.weather_shield_thickness > 0 and inputs.wing_tank_width > 0 and inputs.wing_tank_height_ratio < 1.0:
        db = inputs.double_bottom_height if inputs.double_bottom_height is not None else 0.0
        tank_od = tanks.outer_diameter
        cargo_tank_bottom = db + inputs.tank_support_height
        wing_tank_top = cargo_tank_bottom + inputs.wing_tank_height_ratio * tank_od
        cargo_tank_top = cargo_tank_bottom + tank_od
        shield_top = cargo_tank_top + inputs.weather_shield_clearance
        shield_height = shield_top - wing_tank_top
        tank_zone_length = inputs.loa - inputs.bow_non_tank_length - inputs.stern_non_tank_length
        t_shield = inputs.weather_shield_thickness / 1000.0

        # Top plate: beam × tank zone length
        top_plate_area = inputs.beam * tank_zone_length
        # Side walls: 2 × shield height × tank zone length
        side_wall_area = 2.0 * shield_height * tank_zone_length
        # Forward and aft bulkheads: 2 × beam × shield height
        end_wall_area = 2.0 * inputs.beam * shield_height

        total_shield_area = top_plate_area + side_wall_area + end_wall_area
        w_weather_shield = total_shield_area * t_shield * steel_density

    # --- Top-down vs bottom-up steel ---
    # Moulded depth = wing plate level (uniform moulded depth)
    db_td = inputs.double_bottom_height if inputs.double_bottom_height is not None else 0.0
    cargo_tank_bottom_td = db_td + inputs.tank_support_height
    wing_tank_top_td = cargo_tank_bottom_td + inputs.wing_tank_height_ratio * tanks.outer_diameter
    moulded_depth = max(inputs.depth, wing_tank_top_td) if inputs.wing_tank_width > 0 else inputs.depth
    moulded_volume = inputs.loa * inputs.beam * moulded_depth
    steel_top_down = inputs.steel_rate_per_cbm * moulded_volume

    # Bottom-up: hull steel only (excluding tanks — tanks are separate)
    steel_bottom_up = (w_hull_total + w_wing_plate + w_weather_shield)
    steel_delta = steel_top_down - steel_bottom_up

    # --- Piping & machinery (based on top-down steel + tanks) ---
    w_piping = inputs.piping_factor * (steel_top_down + w_tank_total)

    # --- Outfitting (percentage of steel + tanks) ---
    w_outfitting = inputs.outfitting_factor * (steel_top_down + w_tank_total)

    # --- Lightship total (top-down hull steel + bottom-up tanks + insulation + piping + outfitting) ---
    lightship = steel_top_down + w_tank_total + w_insulation + w_piping + w_outfitting

    return WeightBreakdown(
        hull_bottom_plating=w_bottom,
        hull_side_plating=w_side,
        hull_deck_plating=w_deck,
        hull_rake_plating=w_rake,
        hull_internal_structure=w_structure,
        hull_steel_total=w_hull_total,
        tank_shells=w_tank_shells,
        tank_internals_supports=w_tank_internals,
        tank_total=w_tank_total,
        insulation=w_insulation,
        wing_plate=w_wing_plate,
        weather_shield=w_weather_shield,
        piping_machinery=w_piping,
        outfitting=w_outfitting,
        # Consumables (diesel/fresh water/provisions) are deadweight, not lightship.
        # Explicit zero allowance for now — a proper stores model is tracked separately.
        stores=0.0,
        moulded_volume=moulded_volume,
        moulded_depth=moulded_depth,
        steel_top_down=steel_top_down,
        steel_bottom_up=steel_bottom_up,
        steel_delta=steel_delta,
        lightship=lightship,
    )
