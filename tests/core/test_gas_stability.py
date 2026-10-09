"""Gas-barge intact stability. Independent oracles: closed-form box formulas, not the module."""
import math

import pytest

from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute as capacity
from vessel_designer.core.gas_arrangement import fit
from vessel_designer.core.gas_stability import assess, box_gz, criteria_set_for, segment_fill


@pytest.mark.parametrize("deg", [2, 5, 10, 15, 20])
def test_gz_matches_the_wall_sided_formula_before_deck_edge(deg):
    B, D, T, KG = 14.8, 6.0, 3.0, 4.0               # deck edge immerses at 22.1 deg
    bm = B * B / (12 * T)
    gm = T / 2 + bm - KG
    phi = math.radians(deg)
    assert box_gz(B, D, T, KG, deg) == pytest.approx(math.sin(phi) * (gm + bm / 2 * math.tan(phi) ** 2), abs=1e-6)


def test_gz_is_antisymmetric_and_falls_past_the_deck_edge():
    B, D, T, KG = 14.8, 4.0, 3.0, 3.5
    assert box_gz(B, D, T, KG, -12) == pytest.approx(-box_gz(B, D, T, KG, 12))
    wall_sided_40 = math.sin(math.radians(40)) * (T / 2 + B * B / (12 * T) - KG + B * B / (24 * T) * math.tan(math.radians(40)) ** 2)
    assert box_gz(B, D, T, KG, 40) < wall_sided_40    # deck immersed: less than the wall-sided value


def test_half_full_cylinder_segment():
    h, ybar = segment_fill(2.0, 0.5)
    assert h == pytest.approx(2.0)
    assert ybar == pytest.approx(2.0 - 4 * 2.0 / (3 * math.pi))


def test_cn_ii_passes_the_is_code():
    f = fit(90.0, 14.8, "LPG_propane", 4.4, depths=[6.5], ruleset="IGC_2G", fill_ratio=0.95)
    a = assess(f.engine_result, f.payload_t, criteria_set="IS_CODE_2008")
    assert a.ok
    assert {c.name for c in a.conditions} == {"Laden", "Half laden", "Light"}


def test_narrow_deep_gas_barge_fails_and_half_laden_governs():
    """The check must be able to fail: a 7 m beam on a 6 m deep hull is tender."""
    f = fit(60.0, 7.0, "LPG_propane", 10.0, depths=[6.0], ruleset="IGC_2G_EXACT",
            fill_ratio=0.98, self_propelled=False)
    a = assess(f.engine_result, f.payload_t, criteria_set="IS_CODE_2008")
    assert not a.ok
    assert a.governing.name == "Half laden" and a.governing.gm_fluid_m < 0


def test_adn_extra_criteria_only_for_wide_tanks():
    f = fit(110.0, 11.4, "LNG", 3.0, depths=[4.5], ruleset="ADN_G", fill_ratio=0.95,
            adn_tank_cap_m3=380.0, self_propelled=False)
    a = assess(f.engine_result, f.payload_t, criteria_set=criteria_set_for("ADN_G"))
    wide = f.tank_od_m > 0.70 * 11.4
    names = {x.name for x in a.conditions[0].criteria}
    assert ("Area 0–27°" in names) == wide


def test_bulk_result_is_refused():
    r = capacity(BargeCapacityInputs(loa=60, beam=11, depth=4, cargo_type="bauxite"))
    with pytest.raises(ValueError):
        assess(r, 1000.0)
