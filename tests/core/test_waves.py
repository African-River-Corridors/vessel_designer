"""Test triad for added resistance in waves (STAwave-1): golden, property, feasibility.

Run from engine/:
    python3 -c "import tests.test_waves as t; \
      [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""
import math

from vessel_designer.core.waves import (
    GRAVITY,
    LAMBDA_OVER_LPP_MAX,
    WaveResistanceInputs,
    compute,
)

# The sea leg: NGL laden, Ankobra mouth to Takoradi, 43.2 nm.
SEA = dict(beam_waterline_m=14.8, lpp_m=87.3, speed_kn=8.5)


# --- golden ---------------------------------------------------------------------------

def test_golden_stawave1_reproduces_its_own_formula():
    """R = (1/16) rho g Hs^2 B sqrt(B/L_BWL), by hand, in kN."""
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.0, **SEA))
    lbwl = 0.2 * 87.3
    expect = (1 / 16) * 1025.0 * GRAVITY * 1.0 ** 2 * 14.8 * math.sqrt(14.8 / lbwl) / 1000.0
    assert abs(r.added_resistance_head_seas_kn - expect) < 1e-9


def test_golden_calm_water_is_zero():
    r = compute(WaveResistanceInputs(significant_wave_height_m=0.0, **SEA))
    assert r.added_resistance_kn == 0.0
    assert r.added_power_kw == 0.0


def test_golden_one_metre_head_seas_on_the_ngl_hull():
    """The case that prompted the module. Anchors the magnitude so a refactor cannot move
    it silently: order 10 kN, not 1 and not 100."""
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.0, **SEA))
    assert 5.0 < r.added_resistance_kn < 20.0, r.added_resistance_kn
    assert r.heading_factor == 1.0


# --- property -------------------------------------------------------------------------

def test_property_scales_with_the_square_of_wave_height():
    a = compute(WaveResistanceInputs(significant_wave_height_m=1.0, **SEA)).added_resistance_kn
    b = compute(WaveResistanceInputs(significant_wave_height_m=2.0, **SEA)).added_resistance_kn
    assert abs(b / a - 4.0) < 1e-9, (a, b)


def test_property_monotone_in_wave_height():
    prev = -1.0
    for hs in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r = compute(WaveResistanceInputs(significant_wave_height_m=hs, **SEA))
        assert r.added_resistance_kn >= prev
        prev = r.added_resistance_kn


def test_property_heading_reduces_it_to_zero_abeam():
    full = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                        heading_deg_off_bow=0.0, **SEA)).added_resistance_kn
    beam = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                        heading_deg_off_bow=90.0, **SEA)).added_resistance_kn
    mid = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                       heading_deg_off_bow=60.0, **SEA)).added_resistance_kn
    assert beam == 0.0
    assert 0.0 < mid < full


def test_property_a_blunter_bow_costs_more():
    """L_BWL smaller = blunter = more added resistance. The default 0.2*Lpp is the blunt,
    conservative end, and a finer bow must come out cheaper."""
    blunt = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                         bow_waterline_length_m=0.15 * 87.3,
                                         **SEA)).added_resistance_kn
    fine = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                        bow_waterline_length_m=0.30 * 87.3,
                                        **SEA)).added_resistance_kn
    assert blunt > fine


def test_property_added_power_is_resistance_times_speed():
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.2, **SEA))
    assert abs(r.added_power_kw - r.added_resistance_kn * 8.5 * 0.514444) < 1e-9


# --- feasibility: the validity limits must fire -----------------------------------------

def test_feasibility_long_waves_are_flagged_as_underprediction():
    """STAwave-1 holds for SHORT waves. A 10 s swell on an 87 m hull is lambda/Lpp ~ 1.8,
    deep in the region where it under-predicts — the sheet must say so."""
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                     peak_wave_period_s=10.0, **SEA))
    assert r.lambda_over_lpp > LAMBDA_OVER_LPP_MAX
    c = [c for c in r.checks if c.name == "stawave1_short_wave_validity"][0]
    assert not c.ok
    assert "UNDER-predicts" in c.message


def test_feasibility_short_steep_sea_is_inside_validity():
    r = compute(WaveResistanceInputs(significant_wave_height_m=0.8,
                                     peak_wave_period_s=4.0, **SEA))
    assert r.lambda_over_lpp < LAMBDA_OVER_LPP_MAX
    assert [c for c in r.checks if c.name == "stawave1_short_wave_validity"][0].ok


def test_feasibility_assumed_bow_length_is_declared():
    """If L_BWL was not supplied the result must SAY it assumed one, not quietly use it."""
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.0, **SEA))
    c = [c for c in r.checks if c.name == "bow_length_supplied"][0]
    assert not c.ok
    assert "assumed" in c.message
    assert abs(r.bow_waterline_length_m - 0.2 * 87.3) < 1e-9


def test_feasibility_beam_seas_are_declared_a_floor():
    r = compute(WaveResistanceInputs(significant_wave_height_m=1.0,
                                     heading_deg_off_bow=90.0, **SEA))
    assert any("FLOOR" in w for w in r.warnings)


def test_feasibility_big_seas_leave_the_screening_range():
    r = compute(WaveResistanceInputs(significant_wave_height_m=4.0, **SEA))
    assert not [c for c in r.checks
                if c.name == "wave_height_within_screening_range"][0].ok
