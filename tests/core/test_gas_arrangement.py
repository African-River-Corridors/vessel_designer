"""Benchmarks for the gas arrangement search, reproduced natively from an earlier project wrapper.

The river-side code depends on these numbers, so they are pinned here.
"""
import pytest

from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute as capacity
from vessel_designer.core.gas_arrangement import fit, required_side_clearance, smallest_viable_loa


def test_cn_ii_benchmark_is_reproduced():
    """Ankobra CN II gas figure: 90 x 14.8 x 6.5 m, propane, T 4.4 m, IGC 2G, fill 0.95."""
    f = fit(90.0, 14.8, "LPG_propane", 4.4, depths=[6.5], ruleset="IGC_2G", fill_ratio=0.95)
    assert abs(f.payload_t - 2058) < 1.0
    assert f.n_tanks_wide == 1


def test_search_beats_the_auto_seed_on_cn_ii():
    """Defect 1: the engine's AUTO arrangement lands on the worse fixed point at 14.8 m beam."""
    auto = capacity(BargeCapacityInputs(loa=90, beam=14.8, depth=6.5, cargo_type="LPG_propane"))
    best = fit(90.0, 14.8, "LPG_propane", 4.4, depths=[6.5])
    assert best.payload_t > 1.5 * min(auto.cargo_capacity_t, 3000)


@pytest.mark.parametrize("L,B", [(60, 14.8), (90, 18.0), (100, 20.0)])
def test_capped_tank_respects_side_clearance(L, B):
    """A tank put on the 12 m cap keeps at least the code's side clearance for its volume."""
    f = fit(float(L), B, "LNG", 3.0)
    need = required_side_clearance("IGC_2G", B, f.containment_inner_volume_m3,
                                   f.per_tank_volume_m3, 350.0)
    assert f.tank_od_m <= 12.0 + 1e-6
    assert f.side_clearance_m + 1e-6 >= need


def test_gas_barge_needs_a_hull_longer_than_its_stern_block():
    short = fit(22.0, 12.0, "LNG", 3.0)
    assert short.payload_t == 0 and short.binding == "no cargo area"
    viable = smallest_viable_loa(12.0, "LNG", 3.0)
    assert viable > short.stern_void_m
    assert fit(viable + 5, 12.0, "LNG", 3.0).payload_t > 0


def test_payload_never_exceeds_the_draught_cap():
    f = fit(90.0, 12.9, "LNG", 3.0)
    assert f.draft_at_payload_m <= 3.0 + 1e-6


# Regression snapshot: IGC_2G_EXACT, fill 0.98, T 3.0 m, self-propelled, LNG.
# 120 x 18 was re-pinned from 2,922 t (2 x 8.0 m tanks) to 2,813 t (1 x 11.0 m) by the
# pass-first fix (issue #6): the old design had 0.48 m side clearance, below the 0.80 m
# inland type-G floor (cl. 3.5.2), an error-severity check.
SNAPSHOT = [((90, 12.9), 1505), ((90, 14.8), 1738), ((90, 18.0), 2033), ((120, 18.0), 2813)]


@pytest.mark.parametrize("dims,expected", SNAPSHOT)
def test_regression_snapshot(dims, expected):
    L, B = dims
    f = fit(float(L), B, "LNG", 3.0, ruleset="IGC_2G_EXACT", fill_ratio=0.98)
    assert abs(f.payload_t - expected) < 1.0, f.payload_t


def test_snapshot_120x18_is_one_11m_tank():
    """Was 2 x 8 m abreast, which breaks the type-G side-clearance floor (issue #6)."""
    f = fit(120.0, 18.0, "LNG", 3.0, ruleset="IGC_2G_EXACT", fill_ratio=0.98)
    assert f.feasible
    assert f.n_tanks_wide == 1 and abs(f.tank_od_m - 11.0) < 0.05


def test_cn_ii_free_depth_picks_a_passing_hull():
    """Issue #6: CN II at a 4.4 m draught limit, depth free. The top-tonnage candidate was a
    3.5 m-deep hull at 3.50 m draught -- zero freeboard, overloaded. It must not win."""
    f = fit(90.0, 14.8, "LPG_propane", 4.4, ruleset="IGC_2G", fill_ratio=0.95)
    assert f.feasible
    assert not any(m.startswith(("not_overloaded", "freeboard_ok")) for m in f.failed_checks)
    assert f.depth_m - f.draft_at_payload_m >= 0.3 - 1e-6       # the engine's minimum freeboard
    assert f.draft_at_payload_m <= 4.4 + 1e-6
    assert not (f.depth_m == 3.5 and abs(f.draft_at_payload_m - 3.5) < 1e-3)


def test_no_passing_candidate_is_flagged_infeasible():
    """Only the 0.48 m-clearance 2-abreast design is on offer: returned, but flagged."""
    f = fit(120.0, 18.0, "LNG", 3.0, ruleset="IGC_2G_EXACT", fill_ratio=0.98,
            depths=[5.75], tanks_wide=(2,), extra_clearance_m=())
    assert not f.feasible
    assert any(m.startswith("side_clearance_type_g_floor") for m in f.failed_checks)


def test_nothing_fits_is_infeasible():
    assert not fit(22.0, 12.0, "LNG", 3.0).feasible


def test_adn_tanks_respect_the_per_tank_cap():
    f = fit(110.0, 11.4, "LNG", 3.0, ruleset="ADN_G", fill_ratio=0.95, adn_tank_cap_m3=380.0)
    assert f.payload_t > 0
    assert f.per_tank_volume_m3 <= 380.0 + 1e-6
    assert f.n_tanks_long > 2


def test_settings_are_arguments_not_globals():
    a = fit(90.0, 14.8, "LNG", 3.0, ruleset="IGC_2G_EXACT", fill_ratio=0.98)
    b = fit(90.0, 14.8, "LNG", 3.0, ruleset="IGC_2G", fill_ratio=0.95)
    c = fit(90.0, 14.8, "LNG", 3.0, ruleset="IGC_2G_EXACT", fill_ratio=0.98)
    assert a.payload_t == c.payload_t != b.payload_t
