"""IMO Type C horizontal cylindrical tank geometry and arrangement.

Models horizontal pressure vessels with hemispherical or 2:1 ellipsoidal
dished heads, arranged in rows (abreast) and columns (along the length)
on a barge deck.
"""

import math
from dataclasses import dataclass
from typing import Tuple

from .models import BargeInputs, TankResult


def calculate_tank_arrangement(inputs: BargeInputs) -> TankResult:
    """Calculate tank dimensions, volumes, and weights for the given barge inputs.

    Tank sizing logic:
    1. Available beam = beam - 2 * side_clearance
    2. Total width for tanks = available_beam - (n_wide - 1) * gap_transverse
    3. Outer diameter = total_width / n_wide
    4. Available length = LOA - non_tank_length
    5. Total length for tanks = available_length - (n_long - 1) * gap_longitudinal
    6. Length per tank = total_length / n_long
    7. Cylinder length = tank_length - 2 * head_length
    """
    # Guard None values (auto-optimization may not have run yet)
    side_clearance = inputs.side_clearance if inputs.side_clearance is not None else 0.0
    double_bottom_height = inputs.double_bottom_height if inputs.double_bottom_height is not None else 0.0

    n_wide = inputs.n_tanks_wide
    n_long = inputs.n_tanks_long
    n_total = n_wide * n_long

    # --- Transverse (beam) sizing ---
    available_beam = inputs.beam - 2.0 * side_clearance
    tank_width_total = available_beam - (n_wide - 1) * inputs.tank_gap_transverse
    outer_diameter = tank_width_total / n_wide

    if outer_diameter <= 0:
        raise ValueError(
            f"Tank outer diameter is {outer_diameter:.2f}m - not enough beam. "
            f"Beam={inputs.beam}m, side_clearance={inputs.side_clearance}m, "
            f"n_wide={n_wide}, gap_transverse={inputs.tank_gap_transverse}m"
        )

    outer_radius = outer_diameter / 2.0

    # --- Wall thickness determination ---
    if inputs.tank_wall_thickness is not None:
        # User-provided fixed thickness (backward compatible)
        wall_cyl_mm = inputs.tank_wall_thickness
        wall_head_mm = inputs.tank_wall_thickness
    else:
        # Auto-calculate from pressure vessel formula
        from .pressure_vessel import calculate_wall_thicknesses
        wall_cyl_mm, wall_head_mm = calculate_wall_thicknesses(
            outer_diameter_m=outer_diameter,
            design_pressure_mpa=inputs.design_pressure,
            material_key=inputs.tank_material,
            head_type=inputs.tank_head_type,
            weld_efficiency=inputs.weld_efficiency,
        )

    wall_cyl_m = wall_cyl_mm / 1000.0
    wall_head_m = wall_head_mm / 1000.0
    insulation_m = inputs.insulation_thickness / 1000.0

    # Inner geometry: OD → insulation → steel shell → cargo space
    # Steel shell outer diameter sits inside the insulation
    shell_outer_diameter = outer_diameter - 2.0 * insulation_m
    shell_outer_radius = shell_outer_diameter / 2.0
    inner_diameter = shell_outer_diameter - 2.0 * wall_cyl_m
    inner_radius = inner_diameter / 2.0
    head_inner_radius = shell_outer_radius - wall_head_m

    if inner_radius <= 0:
        raise ValueError(f"Tank inner radius is non-positive. Wall too thick for diameter.")
    if head_inner_radius <= 0:
        raise ValueError(f"Head inner radius is non-positive. Wall too thick for diameter.")

    # --- Head geometry ---
    # Head length uses full OD (the outer envelope including insulation)
    if inputs.tank_head_type == "hemisphere":
        head_length_outer = outer_radius
        # Volume of one hemispherical head (interior, using head wall thickness)
        volume_one_head_inner = (2.0 / 3.0) * math.pi * head_inner_radius**3
        # Surface area of one hemispherical head (steel shell outer)
        sa_one_head_shell = 2.0 * math.pi * shell_outer_radius**2
    elif inputs.tank_head_type == "ellipsoidal_2to1":
        head_length_outer = outer_radius / 2.0
        # Volume of one 2:1 ellipsoidal head (interior, using head wall thickness)
        volume_one_head_inner = (1.0 / 3.0) * math.pi * head_inner_radius**3
        # Surface area approximation for 2:1 ellipsoidal head (steel shell outer)
        sa_one_head_shell = 1.084 * 2.0 * math.pi * shell_outer_radius**2 / 2.0
    else:
        raise ValueError(f"Unknown tank head type: {inputs.tank_head_type}")

    # --- Longitudinal sizing ---
    available_length = inputs.loa - inputs.bow_non_tank_length - inputs.stern_non_tank_length
    tank_length_total = available_length - (n_long - 1) * inputs.tank_gap_longitudinal
    overall_tank_length = tank_length_total / n_long

    cylinder_length = overall_tank_length - 2.0 * head_length_outer

    if cylinder_length <= 0:
        raise ValueError(
            f"Cylinder length is {cylinder_length:.2f}m - tank heads don't fit. "
            f"Available length per tank={overall_tank_length:.2f}m, "
            f"head length={head_length_outer:.2f}m each"
        )

    # --- Interior volumes ---
    # Cylinder (interior)
    volume_cylinder = math.pi * inner_radius**2 * cylinder_length

    # Both heads (interior) - note: cylinder_length already excludes head lengths
    # The cylinder interior length is the same as the outer cylinder length
    # because the heads are dished inward from the outer tank length
    # Actually, the interior cylinder length = overall_tank_length - 2*head_length_outer
    # This is already correct since heads fit within the overall envelope
    volume_heads = 2.0 * volume_one_head_inner

    volume_per_tank = volume_cylinder + volume_heads
    total_tank_volume = n_total * volume_per_tank
    cargo_volume = total_tank_volume * inputs.fill_ratio

    # --- Tank shell weight (steel) ---
    # Cylinder shell: steel sits between shell_outer_radius and inner_radius
    cylinder_sa_shell_outer = 2.0 * math.pi * shell_outer_radius * cylinder_length
    cylinder_sa_inner = 2.0 * math.pi * inner_radius * cylinder_length
    cylinder_shell_volume = (cylinder_sa_shell_outer + cylinder_sa_inner) / 2.0 * wall_cyl_m

    # Head shells (2 per tank, using head wall thickness)
    head_shell_volume = 2.0 * sa_one_head_shell * wall_head_m

    shell_volume_per_tank = cylinder_shell_volume + head_shell_volume
    total_shell_weight = n_total * shell_volume_per_tank * inputs.tank_material_density

    # --- Insulation weight ---
    # Insulation sits between outer_radius (OD envelope) and shell_outer_radius
    cylinder_sa_od = 2.0 * math.pi * outer_radius * cylinder_length
    sa_one_head_od = 2.0 * math.pi * outer_radius**2 if inputs.tank_head_type == "hemisphere" else 1.084 * math.pi * outer_radius**2
    total_od_sa_per_tank = cylinder_sa_od + 2.0 * sa_one_head_od
    insulation_volume_per_tank = total_od_sa_per_tank * insulation_m
    insulation_density_t = inputs.insulation_density / 1000.0  # kg/m^3 to t/m^3
    total_insulation_weight = n_total * insulation_volume_per_tank * insulation_density_t

    # --- Tank top height above keel ---
    tank_top_above_keel = (
        double_bottom_height
        + inputs.tank_support_height
        + outer_diameter
    )

    return TankResult(
        n_tanks_wide=n_wide,
        n_tanks_long=n_long,
        n_tanks_total=n_total,
        outer_diameter=outer_diameter,
        inner_diameter=inner_diameter,
        overall_tank_length=overall_tank_length,
        cylinder_length=cylinder_length,
        head_length=head_length_outer,
        volume_per_tank=volume_per_tank,
        volume_cylinder=volume_cylinder,
        volume_heads=volume_heads,
        total_tank_volume=total_tank_volume,
        cargo_volume=cargo_volume,
        tank_shell_weight=total_shell_weight,
        insulation_weight=total_insulation_weight,
        tank_top_above_keel=tank_top_above_keel,
        cylinder_wall_thickness=wall_cyl_mm,
        head_wall_thickness=wall_head_mm,
        design_pressure=inputs.design_pressure,
        tank_material=inputs.tank_material if inputs.tank_wall_thickness is None else "",
    )


def free_surface_moment_cylindrical(
    inner_radius: float,
    cylinder_length: float,
    fill_ratio: float,
    cargo_density: float,
) -> float:
    """Transverse free surface moment for a horizontal cylindrical tank.

    For a horizontal cylinder partially filled, the free surface is a
    rectangle of width = chord length at fill level, length = cylinder length.

    The free surface inertia about the tank centerline:
    I_fs = (1/12) * L * chord^3

    The free surface correction to GM:
    GG' = rho_cargo * I_fs / displacement

    This function returns rho_cargo * I_fs (the numerator), so the caller
    divides by displacement.

    Args:
        inner_radius: Tank inner radius (m)
        cylinder_length: Length of cylindrical section (m)
        fill_ratio: Fill level as fraction (0-1)
        cargo_density: Cargo density (t/m^3)

    Returns:
        Free surface moment = cargo_density * I_fs (t*m)
    """
    r = inner_radius
    # Fill height from bottom of cylinder
    h = fill_ratio * 2.0 * r  # height of liquid

    # Distance from center to liquid surface
    d = r - h  # negative if more than half full

    # Half-chord length at fill level
    if abs(d) >= r:
        return 0.0  # Empty or completely full, no free surface
    half_chord = math.sqrt(r**2 - d**2)
    chord = 2.0 * half_chord

    # Free surface inertia of the rectangular surface
    i_fs = (1.0 / 12.0) * cylinder_length * chord**3

    return cargo_density * i_fs
