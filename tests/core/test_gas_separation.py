"""Gas-code longitudinal separation — golden, property and feasibility checks."""
from vessel_designer.core.gas_separation import (COFFERDAM_MIN_M, OPENING_SETBACK_M,
                                          GasSeparationInputs, compute)


# ---------- golden ----------

def test_golden_defaults():
    """The 2,00 m opening setback governs, not the 0,60 m cofferdam: a deckhouse flush
    with the cargo area could carry no door and no openable window."""
    r = compute(GasSeparationInputs())
    assert abs(r.aft_separation_m - 2.00) < 1e-9
    assert abs(r.cofferdam_m - 0.60) < 1e-9
    assert abs(r.service_space_m - 1.40) < 1e-9
    assert abs(r.fwd_separation_m - 0.50) < 1e-9
    assert abs(r.total_length_taken_m - 2.50) < 1e-9
    assert r.ok


# ---------- property ----------

def test_aft_separation_never_below_either_rule():
    for cd in (0.0, 0.6, 1.5, 3.0):
        for os_ in (0.0, 2.0, 4.0):
            r = compute(GasSeparationInputs(cofferdam_m=cd, opening_setback_m=os_))
            assert r.aft_separation_m >= cd - 1e-9
            assert r.aft_separation_m >= os_ - 1e-9


def test_service_space_is_the_remainder():
    r = compute(GasSeparationInputs(cofferdam_m=0.9, opening_setback_m=3.0))
    assert abs(r.cofferdam_m + r.service_space_m - r.aft_separation_m) < 1e-9


# ---------- feasibility: the checks must fire ----------

def test_thin_cofferdam_fails():
    r = compute(GasSeparationInputs(cofferdam_m=0.4))
    assert any(c.name == "cofferdam_min_width" and not c.ok for c in r.checks)


def test_short_opening_setback_fails():
    r = compute(GasSeparationInputs(cofferdam_m=0.6, opening_setback_m=1.0))
    assert any(c.name == "opening_setback" and not c.ok for c in r.checks)


def test_type_g_side_floor_fires_below_0_80():
    r = compute(GasSeparationInputs(side_clearance_m=0.5, double_bottom_m=1.0))
    assert any(c.name == "side_clearance_type_g_floor" and not c.ok for c in r.checks)


def test_type_g_side_floor_passes_at_the_igc_default():
    r = compute(GasSeparationInputs(side_clearance_m=1.0, double_bottom_m=1.0))
    assert all(c.ok for c in r.checks)


def test_constants_are_the_cited_values():
    assert COFFERDAM_MIN_M == 0.60 and OPENING_SETBACK_M == 2.00
