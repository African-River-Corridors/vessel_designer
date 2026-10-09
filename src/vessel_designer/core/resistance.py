"""Hull resistance, service speed, and fuel efficiency for ATB barge.

Covers three operating environments:
- Open sea (deep water): ITTC 1957 frictional + residuary for bluff bodies
- Confined shallow river (6.5 m deep): Schijf limiting speed, Lackenby shallow water corrections
- Confined creek (8.0 m deep): same confined-water methods, different channel geometry

References:
- ITTC 1957 friction line
- Schijf (1949) limiting speed in confined waterways
- Lackenby (1963) shallow water resistance increase
- Guldhammer-Harvald residuary resistance charts
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .checks import Check, all_ok


# --- Physical constants ---
GRAVITY = 9.81  # m/s^2
KNOTS_TO_MS = 0.5144  # 1 knot = 0.5144 m/s
KW_PER_KN_MS = 1.0  # 1 kN × 1 m/s = 1 kW


@dataclass
class TugInputs:
    """Tug propulsion characteristics."""
    engine_power_kw: float = 2400.0          # Total installed power (kW)
    propulsive_efficiency: float = 0.45       # Overall propulsive coefficient
    sfc_g_per_kwh: float = 195.0             # Specific fuel consumption (g/kWh)
    fuel_density_kg_per_litre: float = 0.845  # Marine diesel density


@dataclass
class EnvironmentInputs:
    """Channel/waterway parameters for one operating environment."""
    name: str = "Open Sea"
    water_depth: float = 50.0                 # m
    channel_width_bottom: float = 1000.0      # Bottom width of trapezoidal channel (m)
    channel_width_surface: float = 1000.0     # Surface width (m)
    bank_slope: float = 3.0                   # Horizontal : vertical
    current_speed_knots: float = 0.0          # Opposing current (knots)
    water_density: float = 1.025              # t/m^3
    is_deep_water: bool = False
    #: Significant wave height. Zero in a river. Non-zero brings waves.compute into the
    #: resistance, replacing the "sea margin the analyst picked" that this engine used to
    #: force on its reader.
    significant_wave_height_m: float = 0.0
    wave_heading_deg_off_bow: float = 0.0
    peak_wave_period_s: float = 0.0
    #: Under-keel clearance to keep BELOW the squatted keel. Squat is what actually limits
    #: speed in a shallow canalised river, and this engine had no model of it: it returned
    #: 9.2 kn for a vessel that squats 1.7 m into 0.40 m of clearance.
    squat_safety_margin_m: float = 0.15
    apply_squat_limit: bool = True               # Skip shallow/confined corrections


def default_environments() -> List[EnvironmentInputs]:
    """Factory for the three standard operating environments."""
    return [
        EnvironmentInputs(
            name="Open Sea",
            water_depth=50.0,
            channel_width_bottom=1000.0,
            channel_width_surface=1000.0,
            current_speed_knots=0.0,
            water_density=1.025,
            is_deep_water=True,
        ),
        EnvironmentInputs(
            name="Confined shallow river",
            water_depth=6.5,
            channel_width_bottom=40.0,
            channel_width_surface=60.0,
            bank_slope=3.0,
            current_speed_knots=1.0,
            water_density=1.0,
        ),
        EnvironmentInputs(
            name="Confined creek",
            water_depth=8.0,
            channel_width_bottom=60.0,
            channel_width_surface=100.0,
            bank_slope=3.0,
            current_speed_knots=0.5,
            water_density=1.0,
        ),
    ]


@dataclass
class ResistanceInputs:
    """All inputs for the resistance calculation."""
    # Vessel parameters
    loa: float = 130.0
    lwl: float = 125.0                        # Waterline length (m)
    beam: float = 24.0
    draft: float = 6.0
    block_coefficient: float = 0.85
    wetted_surface_area: float = 0.0          # m^2; 0 = auto-calculate
    displacement_tonnes: float = 0.0          # tonnes; 0 = auto from Cb

    # Tug
    tug: TugInputs = field(default_factory=TugInputs)

    # Environments
    environments: List[EnvironmentInputs] = field(default_factory=default_environments)

    # Speed range for curves
    speed_min_knots: float = 2.0
    speed_max_knots: float = 12.0
    speed_step_knots: float = 0.5


# --- Results ---

@dataclass
class SpeedPoint:
    """Resistance and power at one speed in one environment."""
    speed_knots: float                    # Speed over ground
    speed_through_water_knots: float      # = SOG + current
    froude_number: float                  # V / sqrt(g * L)
    froude_depth: float                   # V / sqrt(g * h)
    resistance_frictional_kn: float
    resistance_residuary_kn: float
    resistance_shallow_factor: float      # Multiplier from shallow water
    resistance_total_kn: float
    effective_power_kw: float             # R_T * V
    delivered_power_kw: float             # P_E / eta
    fuel_litres_per_hour: float
    fuel_litres_per_nm: float
    power_available: bool                 # delivered_power <= engine power
    resistance_waves_kn: float = 0.0      # STAwave-1 added resistance (waves.py)
    squat_m: float = 0.0                  # maximum squat at this speed (squat.py)
    dynamic_ukc_m: float = float("inf")   # clearance left under the keel at this speed
    squat_limited: bool = False           # True where squat, not power, forbids this speed


@dataclass
class EnvironmentResult:
    """Resistance results for one operating environment."""
    name: str
    limiting_speed_knots: Optional[float]   # Schijf critical speed (None for deep water)
    service_speed_knots: float              # Max speed where power available
    blockage_ratio: float                   # Am / Ac
    speed_curve: List[SpeedPoint]
    # At service speed:
    resistance_at_service_kn: float
    power_at_service_kw: float
    fuel_at_service_lph: float
    fuel_at_service_lpnm: float
    squat_limited_speed_knots: Optional[float] = None   # fastest speed keeping the margin
    service_speed_governed_by: str = "power"            # power | squat | channel


@dataclass
class ResistanceResults:
    """Complete resistance calculation output.

    The single number that leaves this module to size the electric-barge battery is
    ``binding_power_at_service_kw`` — the delivered power at service speed in the
    *binding* (shallowest, lowest service-speed) environment. See the spec
    docs/feasibility/proposals/resistance.md §1 and overview §6.
    """
    inputs: ResistanceInputs
    wetted_surface_area: float
    environments: List[EnvironmentResult]
    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if no error-severity check has failed (warnings don't gate)."""
        return all_ok(self.checks)

    @property
    def binding_environment(self) -> Optional[EnvironmentResult]:
        """The environment that sizes propulsion: the one with the lowest service
        speed (the shallowest/most-confined leg the barge must still make headway in).
        This is the river leg in practice. Returns None if there are no environments.
        """
        if not self.environments:
            return None
        return min(self.environments, key=lambda e: e.service_speed_knots)

    @property
    def binding_power_at_service_kw(self) -> float:
        """Delivered power at service speed in the binding environment.

        THIS is the propulsion power that feeds ``electric_barge`` battery sizing,
        replacing its hard-coded 600 kW. Read this off the result.
        """
        env = self.binding_environment
        return env.power_at_service_kw if env is not None else 0.0


# --- Calculator ---

class ResistanceCalculator:
    """Hull resistance, power, and fuel consumption calculator."""

    def __init__(self, inputs: ResistanceInputs):
        self.inputs = inputs

    def _compute_wetted_surface(self) -> float:
        """Wetted surface area for a box barge (m^2).

        Simple estimate: bottom + two sides submerged to draft.
        S = Lwl * B + 2 * Lwl * T  (flat bottom + vertical sides)
        Apply form factor 1.02 for rake corrections.
        """
        inp = self.inputs
        s = inp.lwl * inp.beam + 2.0 * inp.lwl * inp.draft
        return s * 1.02  # Small correction for rakes

    def _kinematic_viscosity(self, water_density: float) -> float:
        """Kinematic viscosity of water (m^2/s)."""
        if water_density >= 1.02:
            return 1.19e-6  # Seawater at 15°C
        return 1.14e-6  # Fresh water at 15°C

    def _ittc_1957_cf(self, speed_ms: float, lwl: float, nu: float) -> float:
        """ITTC 1957 frictional resistance coefficient.

        Cf = 0.075 / (log10(Rn) - 2)^2
        """
        rn = speed_ms * lwl / nu
        if rn < 1e5:
            return 0.008  # Laminar fallback
        return 0.075 / (math.log10(rn) - 2.0) ** 2

    def _frictional_resistance(self, speed_ms: float, wetted_surface: float,
                                water_density_kg_m3: float, nu: float) -> float:
        """Frictional resistance (kN) using ITTC 1957."""
        cf = self._ittc_1957_cf(speed_ms, self.inputs.lwl, nu)
        rf = 0.5 * water_density_kg_m3 * speed_ms ** 2 * wetted_surface * cf
        return rf / 1000.0  # N to kN

    def _residuary_resistance(self, speed_ms: float, frictional_kn: float) -> float:
        """Residuary resistance for bluff-body barge (kN).

        For Cb > 0.8, residuary is dominated by pressure drag.
        At low Froude numbers (Fn < 0.2, typical barge speeds),
        Cr/Cf ratio is approximately 0.10-0.25.
        Uses empirical fit: Cr = k * Fn^2 where k calibrated for Cb~0.85.
        """
        fn = speed_ms / math.sqrt(GRAVITY * self.inputs.lwl)

        # Empirical ratio Cr/Cf as function of Fn for bluff bodies
        # Low speed: ~10%, rises steeply above Fn=0.15
        if fn < 0.10:
            ratio = 0.10
        elif fn < 0.20:
            ratio = 0.10 + 2.5 * (fn - 0.10) ** 1.5
        else:
            ratio = 0.15 + 8.0 * (fn - 0.20) ** 2

        return frictional_kn * ratio

    def _channel_cross_section(self, env: EnvironmentInputs) -> float:
        """Trapezoidal channel cross-section area (m^2)."""
        return (env.channel_width_bottom + env.channel_width_surface) / 2.0 * env.water_depth

    def _midship_section_area(self) -> float:
        """Midship section area of vessel (m^2)."""
        return self.inputs.beam * self.inputs.draft * self.inputs.block_coefficient

    def _schijf_limiting_speed(self, env: EnvironmentInputs) -> Optional[float]:
        """Schijf (1949) critical speed in a confined waterway (knots).

        The limiting Froude depth number is found from:
        Fnh_crit = sqrt(2/3) * (1 - n)^(1/3)
        where n = Am/Ac (blockage ratio).
        """
        if env.is_deep_water:
            return None

        ac = self._channel_cross_section(env)
        am = self._midship_section_area()

        if ac <= 0 or am >= ac:
            return 0.0

        n = am / ac
        fnh_crit = math.sqrt(2.0 / 3.0) * (1.0 - n) ** (1.0 / 3.0)
        v_limit = fnh_crit * math.sqrt(GRAVITY * env.water_depth)
        return v_limit / KNOTS_TO_MS

    def _shallow_water_factor(self, speed_ms: float, env: EnvironmentInputs) -> float:
        """Shallow and confined water resistance increase factor.

        Combines:
        1. Lackenby depth correction: f(T/h, Fnh)
        2. Blockage correction: f(n, Fnh)

        Returns multiplier >= 1.0 on total deep-water resistance.
        """
        if env.is_deep_water:
            return 1.0

        h = env.water_depth
        T = self.inputs.draft
        if h <= 0 or T <= 0:
            return 1.0

        fnh = speed_ms / math.sqrt(GRAVITY * h)
        th_ratio = T / h

        # 1. Lackenby shallow water correction
        # Parameterised from Lackenby (1963) data:
        # delta = a * (T/h)^b * Fnh^c
        # Fitted: a=1.4, b=1.5, c=2.5
        if fnh < 0.95:
            lackenby = 1.4 * (th_ratio ** 1.5) * (fnh ** 2.5)
        else:
            lackenby = 5.0  # Near critical speed, massive resistance increase

        # 2. Blockage correction
        ac = self._channel_cross_section(env)
        am = self._midship_section_area()
        if ac > 0:
            n = am / ac
            # Empirical: blockage adds n * fnh^2 factor
            blockage = 2.0 * n * fnh ** 2
        else:
            blockage = 0.0

        return 1.0 + lackenby + blockage

    def _fuel_consumption(self, delivered_power_kw: float, speed_knots: float) -> tuple:
        """Fuel consumption in litres/hour and litres/nautical mile."""
        tug = self.inputs.tug
        fuel_g_per_hr = delivered_power_kw * tug.sfc_g_per_kwh
        fuel_l_per_hr = fuel_g_per_hr / (tug.fuel_density_kg_per_litre * 1000.0)
        if speed_knots > 0:
            fuel_l_per_nm = fuel_l_per_hr / speed_knots
        else:
            fuel_l_per_nm = 0.0
        return fuel_l_per_hr, fuel_l_per_nm

    def _compute_speed_point(self, speed_knots: float, env: EnvironmentInputs,
                              wetted_surface: float) -> SpeedPoint:
        """Compute resistance and power at one speed in one environment."""
        speed_over_ground = speed_knots
        speed_through_water = speed_knots + env.current_speed_knots
        v = speed_through_water * KNOTS_TO_MS  # m/s

        if v <= 0:
            return SpeedPoint(
                speed_knots=speed_knots,
                speed_through_water_knots=speed_through_water,
                froude_number=0.0, froude_depth=0.0,
                resistance_frictional_kn=0.0, resistance_residuary_kn=0.0,
                resistance_shallow_factor=1.0, resistance_total_kn=0.0,
                effective_power_kw=0.0, delivered_power_kw=0.0,
                fuel_litres_per_hour=0.0, fuel_litres_per_nm=0.0,
                power_available=True,
            )

        fn = v / math.sqrt(GRAVITY * self.inputs.lwl)
        fnh = v / math.sqrt(GRAVITY * env.water_depth)

        nu = self._kinematic_viscosity(env.water_density)
        rho = env.water_density * 1000.0  # t/m^3 to kg/m^3

        # Deep-water resistance components
        rf = self._frictional_resistance(v, wetted_surface, rho, nu)
        rr = self._residuary_resistance(v, rf)
        r_deep = rf + rr

        # Shallow/confined correction
        shallow_factor = self._shallow_water_factor(v, env)
        r_total = r_deep * shallow_factor

        # ADDED RESISTANCE IN WAVES (waves.py, STAwave-1). Zero in a river. This replaces the
        # "sea margin" a reader previously had to supply for themselves.
        r_waves = 0.0
        if env.significant_wave_height_m > 0:
            from .waves import WaveResistanceInputs, compute as _wave
            r_waves = _wave(WaveResistanceInputs(
                significant_wave_height_m=env.significant_wave_height_m,
                beam_waterline_m=self.inputs.beam, lpp_m=self.inputs.lwl,
                heading_deg_off_bow=env.wave_heading_deg_off_bow,
                peak_wave_period_s=env.peak_wave_period_s,
                water_density_t_m3=env.water_density,
                speed_kn=speed_through_water)).added_resistance_kn
        r_total += r_waves

        # SQUAT (squat.py). Not a resistance term — a DEPTH term. It decides whether this
        # speed is available at all, which in the Ankobra channel binds long before power.
        sq = 0.0
        dyn_ukc = float("inf")
        squat_limited = False
        if env.apply_squat_limit and env.water_depth > 0 and not env.is_deep_water:
            from .squat import SquatInputs, compute as _squat
            _sr = _squat(SquatInputs(
                speed_through_water_kn=speed_through_water, draft_m=self.inputs.draft,
                beam_m=self.inputs.beam, lpp_m=self.inputs.lwl,
                block_coefficient=self.inputs.block_coefficient,
                water_depth_m=env.water_depth,
                channel_area_m2=self._channel_cross_section(env),
                safety_margin_m=env.squat_safety_margin_m))
            sq, dyn_ukc = _sr.squat_m, _sr.dynamic_ukc_m
            squat_limited = dyn_ukc < env.squat_safety_margin_m

        # Power
        pe = r_total * v  # kW (kN × m/s)
        eta = self.inputs.tug.propulsive_efficiency
        pd = pe / eta if eta > 0 else pe

        # Fuel
        lph, lpnm = self._fuel_consumption(pd, speed_over_ground)

        return SpeedPoint(
            speed_knots=speed_knots,
            speed_through_water_knots=speed_through_water,
            froude_number=fn,
            froude_depth=fnh,
            resistance_frictional_kn=rf,
            resistance_residuary_kn=rr,
            resistance_shallow_factor=shallow_factor,
            resistance_total_kn=r_total,
            effective_power_kw=pe,
            delivered_power_kw=pd,
            resistance_waves_kn=r_waves,
            squat_m=sq,
            dynamic_ukc_m=dyn_ukc,
            squat_limited=squat_limited,
            fuel_litres_per_hour=lph,
            fuel_litres_per_nm=lpnm,
            power_available=pd <= self.inputs.tug.engine_power_kw,
        )

    def _compute_environment(self, env: EnvironmentInputs,
                              wetted_surface: float) -> EnvironmentResult:
        """Full speed sweep for one environment."""
        inp = self.inputs
        limiting = self._schijf_limiting_speed(env)

        # Build speed range
        speeds = []
        s = inp.speed_min_knots
        while s <= inp.speed_max_knots + 0.01:
            speeds.append(round(s, 1))
            s += inp.speed_step_knots

        # Cap at 95% of limiting speed for river environments
        max_eval = inp.speed_max_knots
        if limiting is not None and limiting > 0:
            max_eval = min(max_eval, limiting * 0.95)

        curve = []
        service_speed = 0.0
        service_point = None

        for spd in speeds:
            if spd > max_eval:
                break
            pt = self._compute_speed_point(spd, env, wetted_surface)
            curve.append(pt)
            # A speed is only a SERVICE speed if the vessel can both push it and float at
            # it. Before 2026-09-21 only the first was tested.
            if pt.power_available and not pt.squat_limited and spd > service_speed:
                service_speed = spd
                service_point = pt

        # Blockage ratio
        ac = self._channel_cross_section(env)
        am = self._midship_section_area()
        blockage = am / ac if ac > 0 else 0.0

        # WHAT ACTUALLY GOVERNED THE SERVICE SPEED. Reported rather than inferred, because
        # the three causes call for completely different responses: more power, more depth,
        # or a wider channel.
        sq_limit = None
        if env.apply_squat_limit and env.water_depth > 0 and not env.is_deep_water:
            from .squat import max_speed_for_ukc
            sq_limit = max_speed_for_ukc(
                draft_m=inp.draft, beam_m=inp.beam, lpp_m=inp.lwl,
                water_depth_m=env.water_depth, channel_area_m2=ac,
                block_coefficient=inp.block_coefficient,
                safety_margin_m=env.squat_safety_margin_m)
        # Ask WHY the next step up was refused, rather than comparing the service speed to
        # a threshold. A first attempt tested `service >= squat_limit - 0.05` and reported
        # "power" for a vessel using 35 kW of 425 available — the speed was squat-limited and
        # the label said otherwise, which is the whole failure mode this field exists to stop.
        governed = "power"
        _nxt = [p for p in curve if p.speed_knots > service_speed + 1e-9]
        if _nxt:
            n0 = _nxt[0]
            if n0.squat_limited:
                governed = "squat"
            elif not n0.power_available:
                governed = "power"
        elif limiting is not None and service_speed >= limiting * 0.95 - 0.05:
            governed = "channel"

        if service_point is None and curve:
            service_point = curve[0]
            service_speed = curve[0].speed_knots

        return EnvironmentResult(
            name=env.name,
            limiting_speed_knots=limiting,
            service_speed_knots=service_speed,
            blockage_ratio=blockage,
            speed_curve=curve,
            resistance_at_service_kn=service_point.resistance_total_kn if service_point else 0.0,
            power_at_service_kw=service_point.delivered_power_kw if service_point else 0.0,
            fuel_at_service_lph=service_point.fuel_litres_per_hour if service_point else 0.0,
            fuel_at_service_lpnm=service_point.fuel_litres_per_nm if service_point else 0.0,
            squat_limited_speed_knots=sq_limit,
            service_speed_governed_by=governed,
        )

    def calculate(self) -> ResistanceResults:
        """Run resistance calculations for all environments."""
        # Wetted surface
        if self.inputs.wetted_surface_area > 0:
            ws = self.inputs.wetted_surface_area
        else:
            ws = self._compute_wetted_surface()

        env_results = []
        for env in self.inputs.environments:
            env_results.append(self._compute_environment(env, ws))

        return ResistanceResults(
            inputs=self.inputs,
            wetted_surface_area=ws,
            environments=env_results,
        )


# --- Standardised module contract: checks + free compute() ---


def _build_checks(inputs: ResistanceInputs,
                  environments: List[EnvironmentResult]) -> List[Check]:
    """Validity checks per the spec (docs/feasibility/proposals/resistance.md §4).

    Expressed as data so the UI can render a red/green list and tests can assert.
    """
    checks: List[Check] = []

    for env in environments:
        # service speed must stay under the Schijf limit (where resistance blows up).
        # The sweep already caps at 95% of limiting; this asserts the result honours it.
        if env.limiting_speed_knots is not None and env.limiting_speed_knots > 0:
            ok = env.service_speed_knots <= 0.95 * env.limiting_speed_knots + 1e-6
            checks.append(Check(
                f"service_speed_below_limiting[{env.name}]", ok,
                f"{env.name}: service {env.service_speed_knots:.1f} kn "
                f"<= 0.95 x Schijf limit {env.limiting_speed_knots:.2f} kn",
            ))

        # delivered power at service must be within installed engine power.
        ok_pwr = env.power_at_service_kw <= inputs.tug.engine_power_kw + 1e-6
        checks.append(Check(
            f"power_within_installed[{env.name}]", ok_pwr,
            f"{env.name}: power {env.power_at_service_kw:.0f} kW "
            f"<= installed {inputs.tug.engine_power_kw:.0f} kW",
        ))

        # blockage ratio must be a sane fraction for confined environments
        # (deep-water environments have limiting_speed_knots = None and are skipped).
        if env.limiting_speed_knots is not None:
            ok_block = 0.0 < env.blockage_ratio < 1.0
            checks.append(Check(
                f"blockage_in_range[{env.name}]", ok_block,
                f"{env.name}: blockage n = {env.blockage_ratio:.3f} must be in (0, 1)",
            ))

    # Standing advisory: the empirical residuary/Lackenby/blockage coefficients and the
    # 1.02 form factor are uncalibrated first-order estimates (RS1). ITTC-1957 friction
    # is standard; the rest need a model-test/CFD anchor before any class/board claim.
    checks.append(Check(
        "coefficients_are_first_order", True,
        "Residuary Cr/Cf fit, Lackenby shallow-water, blockage and 1.02 form factor "
        "are uncalibrated first-order estimates (RS1) — ITTC-1957 friction is standard.",
        severity="warning",
    ))

    return checks


def compute(inputs: ResistanceInputs) -> ResistanceResults:
    """Pure free-function entrypoint to the standardised module contract.

    Wraps ``ResistanceCalculator(inputs).calculate()`` (the resistance maths is
    unchanged) and attaches the validity ``checks``. Use ``result.binding_power_at_service_kw``
    as the propulsion-power feed to electric-barge battery sizing.
    """
    result = ResistanceCalculator(inputs).calculate()
    result.checks = _build_checks(inputs, result.environments)
    return result
