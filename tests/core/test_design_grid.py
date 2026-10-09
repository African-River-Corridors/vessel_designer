"""Design-grid sweep: golden base point, tank-count rule, monotonicity."""
import math

from vessel_designer.core.design_grid import (
    sweep, n_tanks_for_length, MAX_TANK_LENGTH_M)


def test_base_point_matches_published():
    """60 m barge x 12 m beam, 1.0 m standard clearance = ~1,311 t.

    RE-BASELINED 2026-09-18 from 1,311 t to 680 t by the DERIVED ARRANGEMENT. A 60 m
    self-propelled gas vessel gives 21.9 m of its length to the stern block and the
    gas-code separation and 9.5 m to the bow rake and end bulkhead, leaving 28.6 m of
    cargo zone instead of 45.0 m. The drop is 48% -- far larger than on the 100 m
    reference vessel (-10%), because the stern block is a FIXED length and a short hull
    pays the same 21.9 m as a long one.

    ** THE PUBLISHED REPORT STILL CARRIES 1,311 t. ** Re-pointing it is a separate,
    deliberate step and it moves a board number, so it is Niall's call, not this test's.

    Earlier history: re-baselined 2026-09-16 from 1,128 t when the propane density was
    corrected from 500 to 581 kg/m3 (saturated liquid at -42.1 C) -- the catalogue was
    carrying an AMBIENT-temperature density under a refrigerated label. Design basis is
    fully refrigerated propane (2026-09-16); the cargo spec is still to be confirmed.
    """
    g = sweep([60], [12.0])
    c = g.curve(60)[0]
    assert c.n_tanks_long == 2
    assert round(c.cargo_t) == 680


def test_tank_count_rule_length_only():
    """Count steps by length only (so each fixed-length curve is smooth)."""
    assert n_tanks_for_length(60) == 2       # base: 2 tanks
    assert n_tanks_for_length(50) == 2
    assert n_tanks_for_length(70) == 2
    assert n_tanks_for_length(80) == 3       # steps up when the hull gets long
    # independent of beam: the sweep uses the same count across all beams
    g = sweep([70], [8.0, 12.0, 16.0])
    assert {c.n_tanks_long for c in g.curve(70)} == {2}


def test_cargo_monotonic_in_length():
    """NARROWED 2026-09-18. Monotonicity in BEAM no longer holds and should not be
    asserted: the MAX_TANK_OD_M = 12 m rule (2026-09-17) switches to two tanks abreast as
    the beam grows, and on a short hull two smaller tanks lose more to their heads than
    the extra beam wins -- 60 m x 16 m carries LESS than 60 m x 12 m. That is the design
    space, not a defect. Monotonicity in LENGTH does still hold, and is the invariant
    worth guarding, because length buys cargo zone one-for-one once the fixed end voids
    are paid. Narrow beams are out of this test's sample: below 11 m the three 40 ft units
    go into two rows, which lengthens the stern block, and short narrow hulls then have no
    cargo zone at all.
    """
    lengths = [70, 80, 90]
    beams = [12.0, 14.0]
    g = sweep(lengths, beams)
    for beam in beams:
        col = [next(c.cargo_t for c in g.curve(loa) if c.beam_m == beam)
               for loa in lengths]
        assert col == sorted(col), f"beam {beam} not monotonic in length: {col}"


def test_short_hulls_are_now_infeasible_for_gas():
    """REPLACES `test_all_cells_feasible_in_design_envelope`, 2026-09-18, and this is a
    FINDING rather than a test edit.

    The old test asserted that the whole reported envelope (45-90 m x 8-16 m) worked. It
    did, when the stern non-cargo zone was 15% of LOA -- 6.75 m on a 45 m hull. Once that
    zone is built from what actually goes in it (a 3.5 m thruster room, two 40 ft units,
    a wheelhouse and a 2.00 m gas-code separation = 21.9 m), a 45 m self-propelled gas
    vessel has no cargo area left at ANY beam in the envelope.

    So the published lower bound of the envelope does not survive the arrangement. Either
    the small vessels are pushed (a barge + separate tug, which moves the crew block off
    the cargo hull) or the envelope starts nearer 55-60 m. That is a design decision --
    Q-ANK gas-sep-2.
    """
    g = sweep([45, 60, 90], [8.0, 12.0, 16.0])
    by_loa = {}
    for c in g.cells:
        by_loa.setdefault(c.barge_length_m, []).append(c)
    assert all(not c.feasible for c in by_loa[45]), "45 m gas vessel should not fit"
    assert all(c.feasible for c in by_loa[60]), [c.reason for c in by_loa[60]]
    assert all(c.feasible for c in by_loa[90]), [c.reason for c in by_loa[90]]
