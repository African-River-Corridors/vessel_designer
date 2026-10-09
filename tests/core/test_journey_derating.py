"""Journey de-rating — golden, property and feasibility checks.

Applies the channel draft cap (T_max = design_depth - UKC) to the volume-bound barge
capacity. See docs/feasibility/proposals/journey-derating.md.
"""
from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute as cap_compute
from vessel_designer.core.journey_derating import JourneyDeratingInputs, compute


def _bauxite_cap(beam=16.0, depth=6.0):
    return cap_compute(BargeCapacityInputs(loa=100.0, beam=beam, depth=depth, cargo_type="bauxite"))


def _derate(cap, design_depth_m, ukc_m=0.5, beam=16.0, depth=6.0):
    return compute(JourneyDeratingInputs(
        capacity=cap, loa=100.0, beam=beam, depth=depth,
        design_depth_m=design_depth_m, ukc_m=ukc_m,
    ))


# ---------- golden ----------

def test_deep_channel_is_volume_bound():
    cap = _bauxite_cap()                       # full-load draft 4.91 m, cap 5083 t
    r = _derate(cap, design_depth_m=5.5, ukc_m=0.5)   # T_max = 5.0 m > 4.91
    assert r.binding_limit == "volume"
    assert abs(r.achievable_tonnage_t - cap.cargo_capacity_t) < 1.0
    assert abs(r.volume_utilisation - 1.0) < 1e-6
    assert r.shed_tonnage_t == 0.0
    assert r.ok


def test_shallow_channel_is_draft_bound():
    cap = _bauxite_cap()                       # full-load draft 4.91 m
    r = _derate(cap, design_depth_m=2.25, ukc_m=0.5)  # T_max = 1.75 m << 4.91
    assert r.binding_limit == "draft"
    assert r.achievable_tonnage_t < cap.cargo_capacity_t
    assert r.shed_tonnage_t > 0.0
    assert r.draft_at_achievable_m == 1.75


# ---------- property ----------

def test_achievable_never_exceeds_capacity():
    cap = _bauxite_cap()
    for dd in (2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
        r = _derate(cap, design_depth_m=dd, ukc_m=0.5)
        assert r.achievable_tonnage_t <= cap.cargo_capacity_t + 1e-6
        assert 0.0 <= r.volume_utilisation <= 1.0 + 1e-9


def test_monotone_in_depth():
    cap = _bauxite_cap()
    last = -1.0
    for dd in (2.0, 3.0, 4.0, 5.0, 6.0):
        r = _derate(cap, design_depth_m=dd, ukc_m=0.5)
        assert r.achievable_tonnage_t >= last - 1e-6   # deeper never carries less
        last = r.achievable_tonnage_t


def test_flip_at_full_load_draft():
    # At T_max exactly == full-load draft, it is volume-bound and carries full capacity.
    cap = _bauxite_cap()
    r = _derate(cap, design_depth_m=cap.full_load_draft_m, ukc_m=0.0)
    assert r.binding_limit == "volume"
    assert abs(r.achievable_tonnage_t - cap.cargo_capacity_t) < 1.0


# ---------- feasibility ----------

def test_utilisation_warning_fires_when_shallow():
    cap = _bauxite_cap()
    r = _derate(cap, design_depth_m=2.25, ukc_m=0.5)
    util = [c for c in r.checks if c.name == "utilisation_reasonable"][0]
    assert not util.ok and util.severity == "warning"
    # warning does not gate result.ok
    assert r.ok == all(c.ok for c in r.checks if c.severity == "error")


def test_floats_fails_when_no_depth():
    cap = _bauxite_cap()
    r = _derate(cap, design_depth_m=0.5, ukc_m=0.5)   # T_max = 0
    floats = [c for c in r.checks if c.name == "floats"][0]
    assert not floats.ok
    assert not r.ok
