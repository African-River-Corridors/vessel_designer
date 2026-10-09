"""ASME Section VIII / IGC Code pressure vessel wall thickness calculation.

Calculates required wall thickness for IMO Type C horizontal cylindrical
tanks based on design pressure, tank diameter, and material properties.

Formulas from ASME Boiler and Pressure Vessel Code, Section VIII, Division 1,
paragraph UG-27, as referenced by the IGC Code Chapter 4 for Type C tanks.
"""

import math
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class TankMaterialProperties:
    """Mechanical and physical properties of a tank material."""

    name: str                       # Display name
    allowable_stress: float         # f, allowable stress (MPa)
    density: float                  # Material density (t/m^3)
    min_thickness: float            # IGC Code minimum thickness after forming (mm)
    corrosion_allowance: float      # Corrosion allowance (mm)
    description: str = ""


TANK_MATERIAL_DATABASE: Dict[str, TankMaterialProperties] = {
    "304L": TankMaterialProperties(
        name="304L Stainless Steel",
        allowable_stress=113.0,
        density=7.93,
        min_thickness=3.0,
        corrosion_allowance=0.0,
        description="Austenitic stainless, LNG/LPG service to -196°C",
    ),
    "316L": TankMaterialProperties(
        name="316L Stainless Steel",
        allowable_stress=113.0,
        density=7.98,
        min_thickness=3.0,
        corrosion_allowance=0.0,
        description="Austenitic stainless, enhanced corrosion resistance",
    ),
    "9Ni": TankMaterialProperties(
        name="9% Nickel Steel",
        allowable_stress=230.0,
        density=7.85,
        min_thickness=5.0,
        corrosion_allowance=0.5,
        description="ASTM A553 Type I, LNG service to -196°C",
    ),
}


def get_tank_material(material_key: str) -> TankMaterialProperties:
    """Look up tank material properties by key."""
    if material_key not in TANK_MATERIAL_DATABASE:
        valid = ", ".join(TANK_MATERIAL_DATABASE.keys())
        raise ValueError(f"Unknown tank material '{material_key}'. Valid: {valid}")
    return TANK_MATERIAL_DATABASE[material_key]


def cylinder_wall_thickness(
    design_pressure_mpa: float,
    inner_radius_mm: float,
    allowable_stress_mpa: float,
    weld_efficiency: float = 0.95,
) -> float:
    """ASME UG-27 circumferential stress formula for cylindrical shells.

    t = P * R / (f * E - 0.6 * P)

    Args:
        design_pressure_mpa: Internal design pressure P (MPa)
        inner_radius_mm: Inner radius R (mm)
        allowable_stress_mpa: Maximum allowable stress f (MPa)
        weld_efficiency: Weld joint efficiency E (0.85-1.0)

    Returns:
        Required wall thickness (mm).
    """
    P = design_pressure_mpa
    R = inner_radius_mm
    f = allowable_stress_mpa
    E = weld_efficiency
    return P * R / (f * E - 0.6 * P)


def hemisphere_head_thickness(
    design_pressure_mpa: float,
    inner_radius_mm: float,
    allowable_stress_mpa: float,
    weld_efficiency: float = 0.95,
) -> float:
    """ASME UG-27 formula for hemispherical heads.

    t = P * R / (2 * f * E - 0.2 * P)

    Args:
        design_pressure_mpa: Internal design pressure P (MPa)
        inner_radius_mm: Inner spherical radius R (mm)
        allowable_stress_mpa: Maximum allowable stress f (MPa)
        weld_efficiency: Weld joint efficiency E (0.85-1.0)

    Returns:
        Required wall thickness (mm).
    """
    P = design_pressure_mpa
    R = inner_radius_mm
    f = allowable_stress_mpa
    E = weld_efficiency
    return P * R / (2.0 * f * E - 0.2 * P)


def ellipsoidal_head_thickness(
    design_pressure_mpa: float,
    inner_diameter_mm: float,
    allowable_stress_mpa: float,
    weld_efficiency: float = 0.95,
) -> float:
    """ASME UG-27 formula for 2:1 ellipsoidal heads.

    t = P * D / (2 * f * E - 0.2 * P)

    Args:
        design_pressure_mpa: Internal design pressure P (MPa)
        inner_diameter_mm: Inner diameter D at head skirt (mm)
        allowable_stress_mpa: Maximum allowable stress f (MPa)
        weld_efficiency: Weld joint efficiency E (0.85-1.0)

    Returns:
        Required wall thickness (mm).
    """
    P = design_pressure_mpa
    D = inner_diameter_mm
    f = allowable_stress_mpa
    E = weld_efficiency
    return P * D / (2.0 * f * E - 0.2 * P)


def calculate_wall_thicknesses(
    outer_diameter_m: float,
    design_pressure_mpa: float,
    material_key: str,
    head_type: str,
    weld_efficiency: float = 0.95,
) -> Tuple[float, float]:
    """Calculate required wall thicknesses for cylinder and heads.

    Uses the outer diameter as a starting point. Since ASME formulas use
    inner radius, iterates once to refine (thin-wall convergence is fast).

    Adds corrosion allowance, rounds up to nearest 0.5mm, and clamps to
    IGC Code minimum thickness.

    Args:
        outer_diameter_m: Tank outer diameter (m)
        design_pressure_mpa: Internal design pressure (MPa)
        material_key: Key into TANK_MATERIAL_DATABASE
        head_type: "hemisphere" or "ellipsoidal_2to1"
        weld_efficiency: Weld joint efficiency (0.85-1.0)

    Returns:
        (cylinder_thickness_mm, head_thickness_mm)
    """
    mat = get_tank_material(material_key)
    outer_radius_mm = outer_diameter_m * 1000.0 / 2.0
    f = mat.allowable_stress
    P = design_pressure_mpa
    E = weld_efficiency

    # First pass: approximate with inner_radius ~ outer_radius
    t_cyl = cylinder_wall_thickness(P, outer_radius_mm, f, E)

    # Second pass: refine with corrected inner radius
    inner_radius_mm = outer_radius_mm - t_cyl
    t_cyl = cylinder_wall_thickness(P, inner_radius_mm, f, E)

    # Head thickness using corrected inner geometry
    inner_diameter_mm = 2.0 * inner_radius_mm
    if head_type == "hemisphere":
        t_head = hemisphere_head_thickness(P, inner_radius_mm, f, E)
    elif head_type == "ellipsoidal_2to1":
        t_head = ellipsoidal_head_thickness(P, inner_diameter_mm, f, E)
    else:
        raise ValueError(f"Unknown head type: {head_type}")

    # Add corrosion allowance
    t_cyl += mat.corrosion_allowance
    t_head += mat.corrosion_allowance

    # Round up to nearest 0.5mm (standard plate sizing)
    t_cyl = math.ceil(t_cyl * 2.0) / 2.0
    t_head = math.ceil(t_head * 2.0) / 2.0

    # Enforce IGC Code minimums
    t_cyl = max(t_cyl, mat.min_thickness)
    t_head = max(t_head, mat.min_thickness)

    return t_cyl, t_head
