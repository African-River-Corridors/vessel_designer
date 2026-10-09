"""Data models for barge design inputs and outputs."""

from dataclasses import dataclass, field
from typing import Optional

from .aft_arrangement import AftArrangementResult
from .gas_separation import GasSeparationResult
from .protective_location import ProtectiveLocationResult


@dataclass
class BargeInputs:
    """All user-provided inputs for ATB LNG/LPG barge design."""

    # --- Principal dimensions ---
    loa: float                          # Length overall (m)
    beam: float                         # Moulded beam (m)
    depth: float                        # Moulded depth (m)
    max_draft: float                    # Maximum design draft (m)
    vertical_clearance: float           # Max height above waterline allowed (m)
    vessel_type: str = "IGC_2G"         # "IGF", "IGC_1G", "IGC_2G", "IGC_3G"

    # --- Rake geometry ---
    bow_rake_length: float = 0.0        # Horizontal length of bow bottom rake (m)
    bow_rake_rise: Optional[float] = None   # Vertical rise of bow rake (m), defaults to depth
    stern_rake_length: float = 0.0      # Horizontal length of stern bottom rake (m)
    stern_rake_rise: Optional[float] = None  # Vertical rise of stern rake (m), defaults to depth

    # --- Tank arrangement constraints ---
    bow_non_tank_pct: float = 0.10      # Forward non-tank zone as fraction of LOA
    stern_non_tank_pct: float = 0.15    # Aft non-tank zone as fraction of LOA
    bow_non_tank_length: Optional[float] = None   # (m) computed from pct; set explicitly to override
    stern_non_tank_length: Optional[float] = None  # (m) computed from pct; set explicitly to override
    wing_tank_width: Optional[float] = None  # Wing ballast tank width per side (m); None = auto (side_clearance − gap)
    wing_tank_gap: float = 0.6          # Gap between wing tank and cargo tank, per side (m)
    wing_tank_height_ratio: float = 0.66  # Wing tank height as fraction of cargo tank OD
    weather_shield_thickness: float = 6.0  # Weather shield plate thickness (mm); 0 = no shield
    weather_shield_clearance: float = 1.5  # Weather shield top above cargo tank top (m)
    dome_height: float = 2.0              # Dome protrusion above cargo tank top (m); extends beyond shield
    side_clearance: Optional[float] = None  # Total side clearance per side (m); auto = wing_tank_width + wing_tank_gap
    tank_gap_transverse: float = 1.0    # Gap between tanks across the beam (m)
    tank_gap_longitudinal: float = 2.0  # Gap between tanks along the length (m)
    n_tanks_wide: int = 1               # Number of tanks abreast
    n_tanks_long: int = 2               # Number of tank rows along the length

    # --- Tank properties ---
    tank_wall_thickness: Optional[float] = 25.0  # Fixed wall thickness (mm); None = auto from pressure vessel formula
    tank_head_type: str = "hemisphere"  # "hemisphere" or "ellipsoidal_2to1"
    tank_material: str = "9Ni"          # Material key: "304L", "316L", "9Ni"
    tank_material_density: float = 7.85 # Tank material density (t/m^3) - 9% nickel steel
    design_pressure: float = 0.5        # Design pressure (MPa), default 5 barg
    weld_efficiency: float = 0.95       # Weld joint efficiency (0.85-1.0)
    tank_structure_factor: float = 1.30 # Internal stiffeners, supports, saddles as multiple of shell weight

    # --- Insulation ---
    insulation_thickness: float = 350.0     # Insulation thickness (mm) — sprayed PU foam
    insulation_density: float = 60.0        # Insulation density (kg/m^3)

    # --- Cargo ---
    cargo_type: str = "LNG_ethane"       # "LNG", "LNG_ethane", "LPG_propane", "LPG_butane", "LPG_mix", or "custom"
    cargo_density_override: Optional[float] = None  # Custom cargo density (kg/m^3), overrides cargo_type lookup
    fill_ratio: float = 0.95            # Maximum fill level (fraction)

    # --- Hull structural assumptions ---
    bottom_plate_thickness: float = 12.0    # Bottom plating thickness (mm)
    side_plate_thickness: float = 10.0      # Side plating thickness (mm)
    deck_plate_thickness: float = 10.0      # Deck plating thickness (mm)
    structure_factor: float = 1.4           # Internal structure weight as multiple of plating
    hull_steel_density: float = 7.85        # Carbon steel density (t/m^3)

    # --- Other ---
    steel_rate_per_cbm: float = 0.10     # Top-down steel weight rate (t/m³ of moulded volume)
    block_coefficient: float = 0.85      # Block coefficient Cb (top-down assumption)
    water_density: float = 1.0          # Water density (t/m^3), 1.0 fresh, 1.025 salt
    underkeel_clearance: float = 0.5    # Required underkeel clearance (m)
    outfitting_factor: float = 0.035     # Outfitting as fraction of (steel + tanks)
    piping_factor: float = 0.04         # Piping & machinery as fraction of (hull + tank weight)
    stores_weight: float = 200.0       # Diesel, fresh water, provisions (tonnes)

    # --- Tank support ---
    tank_support_height: float = 0.5    # Height of tank saddles/supports above inner bottom (m)
    double_bottom_height: Optional[float] = 1.0  # Double bottom height (m); None = auto from protective location

    # --- Arrangement, DRAWING-ONLY pass-through ---
    # These are produced by `barge_capacity` and handed to the drawings by `ga_adapter`.
    # They are never recomputed here: the drawing must plot the arrangement the capacity
    # model costed, or it is a second model wearing the first one's numbers.
    aft_arrangement: Optional[AftArrangementResult] = None
    separation: Optional[GasSeparationResult] = None

    # --- ATB tug (for drawing only, not cargo calculation) ---
    tug_length: float = 25.0            # Tug length extending aft from barge stern (m)
    tug_beam: float = 9.1               # Pusher-tug beam (PRDW); drawings clamp to min(tug_beam, beam) so the tug is never wider than the barge
    notch_depth: float = 3.0            # V-notch cutout depth into stern (m)

    def __post_init__(self):
        if self.bow_rake_rise is None:
            self.bow_rake_rise = self.depth
        if self.stern_rake_rise is None:
            self.stern_rake_rise = self.depth
        # Compute non-tank lengths from percentages if not explicitly set
        if self.bow_non_tank_length is None:
            self.bow_non_tank_length = self.bow_non_tank_pct * self.loa
        if self.stern_non_tank_length is None:
            self.stern_non_tank_length = self.stern_non_tank_pct * self.loa
        # Side clearance per side: default 1.0 m — the standard spacing (IMO IGC Type-C
        # tank, class 2G; the protective-location d(Vc) minimum, decided as the standard
        # basis 7 Jul 2026, replacing the earlier 12%-of-beam simplification). Scenarios
        # may pass a larger explicit value to trade cargo for reduced draft/air draft.
        # The wing ballast tank fills the clearance inboard of the cargo-tank gap, and is
        # kept consistent with whichever clearance applies unless set explicitly.
        if self.side_clearance is None:
            self.side_clearance = 1.0
        if self.wing_tank_width is None:
            self.wing_tank_width = max(0.0, self.side_clearance - self.wing_tank_gap)
        # Sync material density from database when auto-calculating thickness
        if self.tank_wall_thickness is None:
            from .pressure_vessel import get_tank_material
            mat = get_tank_material(self.tank_material)
            self.tank_material_density = mat.density


@dataclass
class TankResult:
    """Results for tank arrangement and geometry."""

    n_tanks_wide: int
    n_tanks_long: int
    n_tanks_total: int
    outer_diameter: float               # m
    inner_diameter: float               # m
    overall_tank_length: float          # Overall length per tank including heads (m)
    cylinder_length: float              # Cylindrical section length (m)
    head_length: float                  # Length of one head (m)
    volume_per_tank: float              # Interior volume per tank (m^3)
    volume_cylinder: float              # Cylinder interior volume per tank (m^3)
    volume_heads: float                 # Both heads interior volume per tank (m^3)
    total_tank_volume: float            # Total interior volume all tanks (m^3)
    cargo_volume: float                 # Usable cargo volume at fill ratio (m^3)
    tank_shell_weight: float            # Weight of all tank shells (tonnes)
    insulation_weight: float            # Weight of all tank insulation (tonnes)
    tank_top_above_keel: float          # Height of tank top above keel (m)
    cylinder_wall_thickness: float = 0.0  # Cylinder wall thickness used (mm)
    head_wall_thickness: float = 0.0      # Head wall thickness used (mm)
    design_pressure: float = 0.0          # Design pressure used (MPa)
    tank_material: str = ""               # Material key used (empty if fixed override)


@dataclass
class WeightBreakdown:
    """Component weight breakdown in tonnes."""

    hull_bottom_plating: float
    hull_side_plating: float
    hull_deck_plating: float
    hull_rake_plating: float
    hull_internal_structure: float
    hull_steel_total: float
    tank_shells: float
    tank_internals_supports: float
    tank_total: float
    insulation: float
    wing_plate: float                   # Horizontal wing plate (steel shelf at wing tank top)
    weather_shield: float               # Weather shield enclosure above wing plate
    piping_machinery: float
    outfitting: float
    stores: float                       # Diesel, fresh water, provisions
    # Top-down vs bottom-up steel comparison
    moulded_volume: float               # LOA × beam × moulded depth (m³)
    moulded_depth: float                # Effective moulded depth to wing plate (m)
    steel_top_down: float               # Top-down: rate × moulded volume (tonnes)
    steel_bottom_up: float              # Bottom-up: sum of all steel components (tonnes)
    steel_delta: float                  # Top-down minus bottom-up (tonnes)
    lightship: float


@dataclass
class StabilityResult:
    """Stability calculation results."""

    KB: float                           # Center of buoyancy above keel (m)
    BM_transverse: float                # Transverse metacentric radius (m)
    KG: float                           # Center of gravity above keel (m)
    GM_solid: float                     # Metacentric height before free surface (m)
    free_surface_correction: float      # Free surface effect on GM (m)
    GM_fluid: float                     # Effective GM after free surface correction (m)
    BM_longitudinal: float              # Longitudinal metacentric radius (m)


@dataclass
class TrimResult:
    """Trim calculation results."""

    LCG: float                          # Longitudinal center of gravity from AP (m)
    LCB: float                          # Longitudinal center of buoyancy from AP (m)
    trim: float                         # Trim (m), positive = bow down
    draft_aft: float                    # Draft at stern (m)
    draft_fwd: float                    # Draft at bow (m)


@dataclass
class BargeResults:
    """Complete barge design calculation results."""

    # Inputs echo
    inputs: BargeInputs

    # Tank arrangement
    tanks: TankResult

    # Cargo
    cargo_type: str
    cargo_density: float                # t/m^3
    cargo_mass: float                   # tonnes

    # Weights
    weights: WeightBreakdown

    # Hydrostatics
    displacement: float                 # tonnes
    deadweight: float                   # tonnes
    draft: float                        # Equilibrium draft (m)
    freeboard: float                    # m
    min_freeboard_ok: bool              # True if freeboard >= 0.3m (typical minimum)

    # Air draft
    air_draft: float                    # Height above waterline to tank top (m), laden
    air_draft_ok: bool                  # True if air_draft <= vertical_clearance

    # Stability
    stability: StabilityResult
    stability_ok: bool                  # True if GM_fluid > 0.15m

    # Trim
    trim: TrimResult

    # Channel depth
    total_depth_required: float         # draft + underkeel clearance (m)

    # Air draft, unladen (lightship rides higher — bridge-critical); defaulted, so at end
    air_draft_unladen: float = 0.0
    # The LIGHT equilibrium draft that unladen air draft is measured from. Carried so a
    # drawing can put the light waterline where the model put it, rather than inferring it.
    light_draft: float = 0.0
    # Air draft with a lifting wheelhouse RAISED — the navigating height, not the transit one.
    air_draft_navigating_unladen: float = 0.0

    # Protective location
    protective_location: Optional[ProtectiveLocationResult] = None

    # Binding constraints (which constraints limit cargo capacity)
    binding_constraints: list = field(default_factory=list)

    # Warnings
    warnings: list = field(default_factory=list)
