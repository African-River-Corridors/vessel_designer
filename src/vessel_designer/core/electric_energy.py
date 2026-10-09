"""Electric-barge energy & service speed from hull resistance in a confined channel.

Couples ``resistance.compute`` — ITTC-1957 friction + residuary + Schijf/Lackenby
confined-water increase, which already depends on **beam, hull shape (Cb, draft)** and
**channel width** (through the blockage ratio n = Am/Ac and the Schijf limiting speed) —
to the **electric drivetrain**:

    shaft (delivered) power  P_D(V)      from resistance  (P_D = R·V / propulsive_coeff)
    battery power            P_bat(V)  = P_D(V) / drivetrain_efficiency
    energy per km            e(V)      = P_bat(V) / V_kmh          [kWh/km]

It returns a speed sweep (resistance, shaft & battery power, energy/km) for each
environment, the **Schijf limiting speed**, a chosen **service speed** (a target cruise
capped safely below the limit), and the energy **per trip / per year** — i.e. the model
for the energy consumption of the electric barge and the speed it can hold.

Pure Python (math only) so it runs client-side in Pyodide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .checks import Check, all_ok
from . import resistance as R

KN_TO_KMH = 1.852


@dataclass
class EnergyInputs:
    # --- barge (beam, shape) ---
    beam: float = 12.0
    loa: float = 80.0
    lwl: float = 78.0
    draft: float = 3.0
    block_coefficient: float = 0.85

    # --- confined design channel (width, depth) ---
    channel_depth_m: float = 4.0
    channel_bottom_width_m: float = 34.0
    channel_top_width_m: float = 58.0
    current_knots: float = 0.5
    fresh_water: bool = True
    also_open_sea: bool = True         # add an open-sea env for comparison

    # --- electric drivetrain ---
    propulsive_coefficient: float = 0.45   # P_D = R·V / PC (hull + propeller)
    drivetrain_efficiency: float = 0.92    # battery → shaft (motor + inverter + line)

    # --- service speed & route ---
    target_service_speed_knots: float = 6.0
    service_speed_safety_fraction: float = 0.9   # cap service speed at this × Schijf limit
    power_margin: float = 1.20             # installed power = P_bat@service × margin
    one_way_km: float = 102.0              # river reach mouth → GCP
    trips_per_year: float = 300.0

    # --- speed sweep for the curves ---
    speed_min_knots: float = 2.0
    speed_max_knots: float = 10.0
    speed_step_knots: float = 0.25


@dataclass
class EnergyPoint:
    speed_knots: float
    speed_kmh: float
    froude_depth: float
    resistance_kn: float
    shaft_power_kw: float       # delivered P_D
    battery_power_kw: float     # P_D / drivetrain_efficiency
    energy_kwh_per_km: float


@dataclass
class EnergyEnvironment:
    name: str
    limiting_speed_knots: Optional[float]
    service_speed_knots: float
    blockage_ratio: float
    curve: List[EnergyPoint]
    # at service speed (interpolated on the curve):
    resistance_kn: float
    shaft_power_kw: float
    battery_power_kw: float
    energy_kwh_per_km: float
    energy_per_trip_kwh: float      # one-way over one_way_km
    energy_per_year_mwh: float      # round trips × trips_per_year


@dataclass
class EnergyResult:
    inputs: EnergyInputs
    installed_power_kw: float
    environments: List[EnergyEnvironment]
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)

    @property
    def binding(self) -> Optional[EnergyEnvironment]:
        """Most-confined environment (lowest service speed) — sizes the barge."""
        return min(self.environments, key=lambda e: e.service_speed_knots) if self.environments else None


def _interp(curve: List[EnergyPoint], v_knots: float, attr: str) -> float:
    """Linear interpolation of a curve attribute at speed v (knots)."""
    if not curve:
        return 0.0
    if v_knots <= curve[0].speed_knots:
        return getattr(curve[0], attr)
    if v_knots >= curve[-1].speed_knots:
        return getattr(curve[-1], attr)
    for a, b in zip(curve, curve[1:]):
        if a.speed_knots <= v_knots <= b.speed_knots:
            t = (v_knots - a.speed_knots) / (b.speed_knots - a.speed_knots or 1.0)
            return getattr(a, attr) + t * (getattr(b, attr) - getattr(a, attr))
    return getattr(curve[-1], attr)


def compute(inp: EnergyInputs) -> EnergyResult:
    # Build the environments and run the (validated) resistance model. Installed engine
    # power is set huge so resistance doesn't cap the sweep — we choose service speed here.
    envs = [R.EnvironmentInputs(
        name="Design channel", water_depth=inp.channel_depth_m,
        channel_width_bottom=inp.channel_bottom_width_m,
        channel_width_surface=inp.channel_top_width_m,
        current_speed_knots=inp.current_knots,
        water_density=1.0 if inp.fresh_water else 1.025)]
    if inp.also_open_sea:
        envs.append(R.EnvironmentInputs(
            name="Open sea", water_depth=50.0, channel_width_bottom=1000.0,
            channel_width_surface=1000.0, is_deep_water=True, water_density=1.025))

    rin = R.ResistanceInputs(
        loa=inp.loa, lwl=inp.lwl, beam=inp.beam, draft=inp.draft,
        block_coefficient=inp.block_coefficient, environments=envs,
        speed_min_knots=inp.speed_min_knots, speed_max_knots=inp.speed_max_knots,
        speed_step_knots=inp.speed_step_knots,
        tug=R.TugInputs(engine_power_kw=1e12, propulsive_efficiency=inp.propulsive_coefficient))
    rres = R.compute(rin)

    energy_envs: List[EnergyEnvironment] = []
    for e in rres.environments:
        curve: List[EnergyPoint] = []
        for p in e.speed_curve:
            v_kmh = p.speed_knots * KN_TO_KMH
            p_bat = p.delivered_power_kw / inp.drivetrain_efficiency
            e_km = p_bat / v_kmh if v_kmh > 0 else 0.0
            curve.append(EnergyPoint(
                speed_knots=p.speed_knots, speed_kmh=v_kmh, froude_depth=p.froude_depth,
                resistance_kn=p.resistance_total_kn, shaft_power_kw=p.delivered_power_kw,
                battery_power_kw=p_bat, energy_kwh_per_km=e_km))

        # service speed: the target cruise, capped safely below the Schijf limit
        v_service = inp.target_service_speed_knots
        if e.limiting_speed_knots and e.limiting_speed_knots > 0:
            v_service = min(v_service, inp.service_speed_safety_fraction * e.limiting_speed_knots)
        if curve:
            v_service = min(v_service, curve[-1].speed_knots)

        e_km = _interp(curve, v_service, "energy_kwh_per_km")
        trip_kwh = e_km * inp.one_way_km
        year_mwh = trip_kwh * 2.0 * inp.trips_per_year / 1000.0
        energy_envs.append(EnergyEnvironment(
            name=e.name, limiting_speed_knots=e.limiting_speed_knots,
            service_speed_knots=round(v_service, 2), blockage_ratio=e.blockage_ratio,
            curve=curve,
            resistance_kn=_interp(curve, v_service, "resistance_kn"),
            shaft_power_kw=_interp(curve, v_service, "shaft_power_kw"),
            battery_power_kw=_interp(curve, v_service, "battery_power_kw"),
            energy_kwh_per_km=e_km, energy_per_trip_kwh=trip_kwh,
            energy_per_year_mwh=year_mwh))

    binding = min(energy_envs, key=lambda x: x.service_speed_knots) if energy_envs else None
    installed = (binding.battery_power_kw * inp.power_margin) if binding else 0.0

    checks: List[Check] = []
    if binding:
        checks.append(Check(
            "service_below_schijf",
            binding.limiting_speed_knots is None or
            binding.service_speed_knots <= binding.limiting_speed_knots + 1e-6,
            f"service {binding.service_speed_knots:.1f} kn stays below the Schijf limit "
            f"{binding.limiting_speed_knots:.1f} kn" if binding.limiting_speed_knots else
            "no confined limit (open water)"))
        checks.append(Check(
            "energy_positive", binding.energy_kwh_per_km > 0,
            f"energy {binding.energy_kwh_per_km:.1f} kWh/km at service speed"))
    checks.append(Check(
        "resistance_coeffs_first_order", True,
        "confined-water resistance (residuary/Lackenby/blockage) is a first-order estimate "
        "(RS1) — ITTC-1957 friction is standard; anchor with a model test/CFD before class use.",
        severity="warning"))

    return EnergyResult(inputs=inp, installed_power_kw=installed,
                        environments=energy_envs, checks=checks)
