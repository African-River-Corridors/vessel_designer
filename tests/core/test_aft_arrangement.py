"""Aft arrangement — golden, property and feasibility checks.

The stern block is what replaced `stern_void_fraction = 0.15`. These tests exist so the
replacement stays a DERIVATION: if someone puts a number back, one of them fails.
"""
from vessel_designer.core.aft_arrangement import (AftArrangementInputs, ISO40_LENGTH_M,
                                           compute)


def _a(**kw):
    kw.setdefault("beam", 14.8)
    kw.setdefault("depth", 5.4)
    return compute(AftArrangementInputs(**kw))


# ---------- golden ----------

def test_golden_block_length():
    """CN II motor vessel, 14.8 m beam, 5.4 m depth.

        thruster room            3.500 m
        + foundation             0.300 m
        + 40 ft units           12.192 m  (3 ABREAST, one row)
        + clear gap              0.300 m
        + wheelhouse             3.600 m
        =                       19.892 m

    The units sit ABREAST, so going from two to three (2026-09-18) does not lengthen the
    block -- it widens the requirement to 10.914 m of beam.
    """
    r = _a()
    assert abs(r.length_m - 19.892) < 1e-3
    assert len(r.container_labels) == 3
    assert abs(r.container_total_width_m - 10.914) < 1e-3
    assert abs(r.container_x1_m - r.container_x0_m - ISO40_LENGTH_M) < 1e-9
    assert [z[0] for z in r.zones] == ["THRUSTER ROOM", "40 FT UNITS (3 ABREAST x 1)",
                                       "WHEELHOUSE (LIFTING)"]
    assert r.ok


def test_golden_heights():
    """Deck 5.40 + 0.30 stool + 2.896 high-cube = 8.596 m to the container roof; the
    wheelhouse STOWS at deck level, so its roof is 5.40 + 3.40 = 8.80 m.

    The 3.40 m wheelhouse (2026-09-18, was 2.80 m) now TOPS the containers, so it — not
    the 40 ft units — sets the transit air draft. Worth knowing: a taller cab is paid for
    at every bridge, stowed or not."""
    r = _a()
    assert abs(r.container_top_above_keel_m - 8.596) < 1e-3
    assert abs(r.wheelhouse_top_lowered_m - 8.80) < 1e-3
    assert abs(r.block_top_lowered_m - 8.80) < 1e-3      # the wheelhouse, not the containers


# ---------- property ----------

def test_three_thrusters_are_symmetric_about_the_centreline():
    r = _a()
    assert len(r.thruster_offsets_m) == 3
    assert abs(sum(r.thruster_offsets_m)) < 1e-9
    assert abs(r.thruster_offsets_m[1]) < 1e-9


def test_length_grows_with_a_longer_thruster_room():
    assert (_a(thruster_room_length_m=5.0).length_m
            - _a(thruster_room_length_m=3.5).length_m) == 1.5


def test_extra_unit_costs_beam_not_length():
    """Units are ABREAST, so a fourth one widens the block and leaves its length alone.
    This is the property that lets the mix differ by cargo for free."""
    three, four = _a(), _a(n_accom_units=3)
    assert abs(three.length_m - four.length_m) < 1e-9
    assert four.container_total_width_m > three.container_total_width_m


def test_length_is_independent_of_the_cargo_it_must_see_over():
    """The LIFT depends on the cargo; the LENGTH must not, or the capacity model would be
    circular (cargo zone -> cargo top -> block length -> cargo zone)."""
    assert (_a(sightline_obstruction_m=20.0).length_m
            == _a(sightline_obstruction_m=None).length_m)


def test_lift_raises_the_eye_over_the_obstruction():
    r = _a(sightline_obstruction_m=12.0)
    eye = r.wheelhouse_floor_raised_m + 1.5
    assert eye >= 12.0 + 0.5 - 1e-9
    assert r.wheelhouse_top_raised_m > r.wheelhouse_top_lowered_m


def test_no_lift_when_there_is_nothing_to_see_over():
    assert _a(sightline_obstruction_m=3.0).wheelhouse_lift_m == 0.0


# ---------- feasibility: the checks must fire ----------

def test_narrow_beam_fits_fewer_thrusters_and_says_so():
    """Three 2.60 m units do not go across a narrow hull at any clearance. The module
    fits what fits and WARNS about the shortfall -- it does not declare the vessel
    impossible, because thruster size is an estimate and gating on it would delete half
    the design grid."""
    r = compute(AftArrangementInputs(beam=8.0, depth=5.0))
    assert len(r.thruster_offsets_m) == 2          # two fit, three do not
    warn = next(c for c in r.checks if c.name == "requested_thruster_count_fits")
    assert not warn.ok and warn.severity == "warning"
    assert "3" in warn.message
    assert r.ok                                     # a warning must not gate the design


def test_a_wide_beam_takes_all_three():
    r = compute(AftArrangementInputs(beam=14.8, depth=5.4))
    assert len(r.thruster_offsets_m) == 3
    assert all(c.ok for c in r.checks)


def test_narrow_beam_stacks_the_units_in_two_rows():
    """Three 40 ft units abreast need 10.91 m. A 10 m hull puts two abreast and the third
    in a second row, which LENGTHENS the stern block -- the real trade, and the reason the
    8 m and 10 m columns of the design grid still exist."""
    wide, narrow = _a(), _a(beam=10.0)
    assert wide.container_rows == 1 and wide.container_per_row == 3
    assert narrow.container_rows == 2 and narrow.container_per_row == 2
    assert narrow.length_m > wide.length_m + 12.0
    warn = next(c for c in narrow.checks if c.name == "units_fit_in_one_row")
    assert not warn.ok and warn.severity == "warning"
    assert narrow.ok


def test_sightline_warns_when_the_column_is_too_short():
    """A cargo top the wheelhouse cannot see over is a real design problem, reported as a
    warning: it is solved by a taller column or a lower tank, not by calling the vessel
    impossible on the strength of an assumed stroke."""
    r = _a(sightline_obstruction_m=30.0, wheelhouse_max_lift_m=2.0)
    c = next(c for c in r.checks if c.name == "wheelhouse_sees_over_cargo")
    assert not c.ok and c.severity == "warning"
    assert r.warnings and r.ok
