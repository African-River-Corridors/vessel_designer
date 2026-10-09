"""Resistance & propulsion power — golden, property and feasibility checks.

The free compute() wraps the unchanged ResistanceCalculator and attaches validity
checks. Golden values freeze the Ankobra-shallow (binding) environment at the default
barge. See docs/feasibility/proposals/resistance.md.
"""
from vessel_designer.core.resistance import (
    ResistanceCalculator,
    ResistanceInputs,
    EnvironmentInputs,
    TugInputs,
    default_environments,
    compute,
)


def _ankobra(r):
    return next(e for e in r.environments if e.name == "Confined shallow river")


# ---------- golden: Ankobra-shallow (binding) environment, default barge ----------

def test_resistance_golden_ankobra_shallow():
    """RE-BASELINED 2026-09-21 when squat entered the model. This is a CORRECTION, not a
    retune: service speed was 9.0 kn and 2,218.9 kW, computed from resistance alone. At 9 kn
    this vessel squats far into a 0.50 m under-keel clearance, so that speed was never
    available. It is now 2.5 kn and 66.2 kW.

    The default case is also, on inspection, physically extreme — see the validity test
    below — so treat these numbers as a regression anchor, not as a design answer.
    """
    r = compute(ResistanceInputs())
    assert abs(r.wetted_surface_area - 4590.0) < 1.0
    a = _ankobra(r)
    assert abs(a.limiting_speed_knots - 10.828) < 0.01     # Schijf limit, unchanged
    assert a.service_speed_knots == 2.5
    assert a.service_speed_governed_by == "squat"
    assert abs(a.power_at_service_kw - 66.2) < 1.0         # delivered power -> battery feed
    assert abs(a.resistance_at_service_kn - 16.54) < 0.1
    assert abs(a.fuel_at_service_lph - 15.27) < 0.5
    assert abs(a.fuel_at_service_lpnm - 6.109) < 0.05


def test_feasibility_the_default_case_is_outside_barrass_validity():
    """The default pairs a 130 x 24 m hull at 6.0 m draft with a 40 m wide, 6.5 m deep
    channel: blockage 0.44 and 0.50 m of water under the keel. Barrass is fitted below about
    0.35. The old model returned 9 knots here without comment; the least this one can do is
    say the combination is not physical."""
    from vessel_designer.core.squat import SquatInputs, compute as squat
    i = ResistanceInputs()
    area = (40.0 + 60.0) / 2 * 6.5
    sr = squat(SquatInputs(speed_through_water_kn=4.0, draft_m=i.draft, beam_m=i.beam,
                           lpp_m=i.lwl, block_coefficient=i.block_coefficient,
                           water_depth_m=6.5, channel_area_m2=area))
    assert sr.blockage_ratio > 0.4, sr.blockage_ratio
    assert not [c for c in sr.checks if c.name == "blockage_within_barrass_range"][0].ok


def test_binding_environment_is_ankobra_and_feeds_battery():
    # The single number that leaves the module for battery sizing.
    r = compute(ResistanceInputs())
    assert r.binding_environment.name == "Confined shallow river"   # lowest service speed
    assert abs(r.binding_power_at_service_kw - 66.2) < 1.0
    assert r.binding_power_at_service_kw == _ankobra(r).power_at_service_kw


def test_checks_pass_on_default_design():
    r = compute(ResistanceInputs())
    assert r.ok                                            # no error-severity failures
    names = {c.name for c in r.checks}
    assert "coefficients_are_first_order" in names
    advisory = next(c for c in r.checks if c.name == "coefficients_are_first_order")
    assert advisory.severity == "warning" and advisory.ok


# ---------- property: the physics that must always hold ----------

def test_resistance_monotone_in_speed():
    r = compute(ResistanceInputs())
    a = _ankobra(r)
    totals = [p.resistance_total_kn for p in a.speed_curve if p.speed_through_water_knots > 0]
    assert all(b >= x - 1e-9 for x, b in zip(totals, totals[1:]))


def test_shallow_factor_at_least_one_and_grows_as_depth_falls():
    # Compare the shallow factor at a fixed speed for two depths.
    calc = ResistanceCalculator(ResistanceInputs())
    deep = EnvironmentInputs(name="d", water_depth=20.0, channel_width_bottom=200.0,
                             channel_width_surface=200.0, water_density=1.0)
    shallow = EnvironmentInputs(name="s", water_depth=8.0, channel_width_bottom=200.0,
                                channel_width_surface=200.0, water_density=1.0)
    v = 4.0  # m/s
    f_deep = calc._shallow_water_factor(v, deep)
    f_shallow = calc._shallow_water_factor(v, shallow)
    assert f_deep >= 1.0 and f_shallow >= 1.0
    assert f_shallow > f_deep


def test_deep_water_factor_is_one():
    calc = ResistanceCalculator(ResistanceInputs())
    env = EnvironmentInputs(name="open", is_deep_water=True)
    assert calc._shallow_water_factor(5.0, env) == 1.0


def test_service_speed_falls_as_channel_gets_shallower():
    def svc(depth):
        env = EnvironmentInputs(name="x", water_depth=depth, channel_width_bottom=40.0,
                                channel_width_surface=60.0, current_speed_knots=1.0,
                                water_density=1.0)
        r = compute(ResistanceInputs(environments=[env]))
        return r.environments[0].service_speed_knots
    assert svc(10.0) >= svc(7.0) >= svc(5.0)


# ---------- feasibility: checks fire when they should ----------

def test_service_speed_check_passes_within_schijf():
    # Default river env: sweep capped at 95% of Schijf, so the check holds.
    r = compute(ResistanceInputs())
    svc_checks = [c for c in r.checks if c.name.startswith("service_speed_below_limiting")]
    assert svc_checks and all(c.ok for c in svc_checks)


def test_blockage_in_range_fires_for_overtight_channel():
    # A channel barely wider than the barge -> n -> 1 (or am >= ac) -> check fails.
    # midship area = 24*6*0.85 = 122.4 m^2; this channel gives ac ~ 110 m^2 -> n > 1.
    tight = EnvironmentInputs(name="tight", water_depth=6.5, channel_width_bottom=16.0,
                              channel_width_surface=18.0, current_speed_knots=0.0,
                              water_density=1.0)
    r = compute(ResistanceInputs(beam=24.0, draft=6.0, environments=[tight]))
    block_checks = [c for c in r.checks if c.name.startswith("blockage_in_range")]
    assert block_checks
    assert not all(c.ok for c in block_checks)             # over-tight -> fires
    assert not r.ok


def test_power_within_installed_fires_when_underpowered():
    # If even the slowest swept speed needs more than the installed power, no speed is
    # power_available; the service point falls back to the slowest, whose delivered power
    # exceeds the engine -> power_within_installed fires. ~5 kW installed forces this
    # (slowest-speed delivered power is ~40 kW).
    weak = TugInputs(engine_power_kw=5.0)
    r = compute(ResistanceInputs(tug=weak))
    pwr_checks = [c for c in r.checks if c.name.startswith("power_within_installed")]
    assert pwr_checks
    assert not all(c.ok for c in pwr_checks)
    assert not r.ok


def test_power_within_installed_passes_when_low_speed_feasible():
    # A modest engine still finds a feasible slow service speed -> check passes.
    r = compute(ResistanceInputs(tug=TugInputs(engine_power_kw=50.0)))
    pwr_checks = [c for c in r.checks if c.name.startswith("power_within_installed")]
    assert pwr_checks and all(c.ok for c in pwr_checks)


# ---------- non-breaking: legacy entrypoint unchanged ----------

def test_legacy_calculator_entrypoint_unchanged():
    legacy = ResistanceCalculator(ResistanceInputs()).calculate()
    free = compute(ResistanceInputs())
    assert legacy.wetted_surface_area == free.wetted_surface_area
    for le, fe in zip(legacy.environments, free.environments):
        assert le.service_speed_knots == fe.service_speed_knots
        assert le.power_at_service_kw == fe.power_at_service_kw
    # calculate() does not attach checks (additive change lives in compute()).
    assert legacy.checks == []
