"""ADN type G as a selectable tank ruleset (2026-10-07). Existing IGC/IGF behaviour unchanged."""
from vessel_designer.core.protective_location import (ADN_G_BOTTOM_M, ADN_G_SIDE_M, ADN_G_DOUBLE_HULL_M,
                                               compute_required_clearances, distance_d_vc)
from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute


def test_adn_g_distances_are_constant_not_volume_stepped():
    for vc in (500.0, 3000.0, 20000.0):
        r = compute_required_clearances("ADN_G", 18.0, distance_d_vc(vc))
        assert r.cs_required == ADN_G_SIDE_M and r.cb_required == ADN_G_BOTTOM_M


def test_igc_2g_unchanged():
    assert compute_required_clearances("IGC_2G", 14.8, 1.0).cs_required == 1.0
    assert compute_required_clearances("IGC_2G", 14.8, 2.0).cb_required == 2.0
    assert compute_required_clearances("IGC_2G", 14.8, 0.8).cb_required == 14.8 / 15.0


def test_adn_g_tank_diameter_follows_its_side_clearance():
    common = dict(loa=90.0, beam=18.0, depth=6.0, cargo_type="LNG", n_tanks_wide=2)
    adn = compute(BargeCapacityInputs(vessel_type="ADN_G", **common))
    assert abs(adn.side_clearance_m - ADN_G_SIDE_M) < 1e-9
    # OD = (beam - 2 cs - 1.0 m transverse gap) / 2
    assert abs(adn.tank_outer_diameter_m - (18.0 - 2 * ADN_G_SIDE_M - 1.0) / 2) < 1e-6


def test_adn_side_includes_double_hull_and_gap():
    assert ADN_G_SIDE_M > ADN_G_DOUBLE_HULL_M          # LNG must sit inside a double hull
    assert abs(ADN_G_SIDE_M - 1.25) < 1e-9 and abs(ADN_G_BOTTOM_M - 1.10) < 1e-9


def test_d_vc_exact_bands():
    from vessel_designer.core.protective_location import d_vc_exact
    assert d_vc_exact(800) == 0.8
    assert abs(d_vc_exact(3000) - 0.9) < 1e-12 and abs(d_vc_exact(5000) - 1.0) < 1e-12
    assert abs(d_vc_exact(10000) - 1.2) < 1e-12 and d_vc_exact(40000) == 2.0


def test_igc_exact_measures_to_steel_and_uses_each_tank():
    from vessel_designer.core.protective_location import d_vc_exact
    r = compute(BargeCapacityInputs(loa=90.0, beam=14.8, depth=6.0, cargo_type="LNG",
                                    n_tanks_wide=1, vessel_type="IGC_2G_EXACT"))
    per_tank = r.containment_inner_volume_m3 / r.n_tanks_total
    # side clearance to the insulation face = d(per tank) - 0.35 m insulation
    assert abs(r.side_clearance_m - (d_vc_exact(per_tank) - 0.35)) < 0.02
    old = compute(BargeCapacityInputs(loa=90.0, beam=14.8, depth=6.0, cargo_type="LNG",
                                      n_tanks_wide=1, vessel_type="IGC_2G"))
    assert r.tank_outer_diameter_m > old.tank_outer_diameter_m
