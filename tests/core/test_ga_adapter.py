"""ga_adapter: the drawing structures are a view of the capacity result, never a second model."""
import math

import pytest

from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute
from vessel_designer.core.ga_adapter import is_gas, to_ga


def _gas_case():
    inp = BargeCapacityInputs(loa=100.0, beam=16.0, depth=6.0, cargo_type="LNG_ethane")
    return inp, compute(inp)


def test_geometry_passes_through_unchanged():
    inp, res = _gas_case()
    gi, gr = to_ga(inp, res)
    assert (gi.loa, gi.beam, gi.depth) == (inp.loa, inp.beam, inp.depth)
    assert gi.max_draft == pytest.approx(res.full_load_draft_m)
    assert gi.n_tanks_wide == res.n_tanks_wide
    assert gi.side_clearance == res.side_clearance_m
    assert gi.bow_non_tank_length == res.bow_void_length_m
    assert gi.stern_non_tank_length == res.stern_void_length_m
    assert gr.cargo_mass == res.cargo_capacity_t
    assert gr.displacement == res.displacement_t


def test_tank_volume_reconciles_with_capacity():
    inp, res = _gas_case()
    _, gr = to_ga(inp, res)
    t = gr.tanks
    assert t.outer_diameter == res.tank_outer_diameter_m
    assert t.total_tank_volume == pytest.approx(res.cargo_volume_m3 / inp.fill_ratio)
    r = t.inner_diameter / 2
    assert t.volume_per_tank == pytest.approx(math.pi * r * r * t.cylinder_length)
    assert math.isnan(t.tank_shell_weight)            # never invents a weight


def test_laden_draft_override_and_tug_flag():
    inp, res = _gas_case()
    gi, gr = to_ga(inp, res, laden_draft_m=2.0, motor_vessel=False)
    assert gi.max_draft == 2.0 and gr.draft == 2.0
    assert gr.freeboard == pytest.approx(inp.depth - 2.0)
    assert gi.tug_length == 25.0
    assert to_ga(inp, res)[0].tug_length == 0.0


def test_bulk_has_no_tank_geometry():
    inp = BargeCapacityInputs(loa=100.0, beam=16.0, depth=6.0, cargo_type="bauxite")
    res = compute(inp)
    assert not is_gas(res)
    _, gr = to_ga(inp, res)
    assert gr.tanks is None
