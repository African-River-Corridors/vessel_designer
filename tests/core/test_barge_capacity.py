"""Unified barge capacity — unit, property and golden checks.

Capacity is VOLUME-BOUND (no weight/draft cap; that is applied downstream). Numbers
match docs/feasibility/barge-cargo-chain.md (LOA 100, beam 16, moulded depth 6).
"""
from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute


def _gas(beam=16.0, depth=6.0, **kw):
    return compute(BargeCapacityInputs(loa=100.0, beam=beam, depth=depth,
                                       cargo_type="LNG_ethane", **kw))


def _bauxite(beam=16.0, depth=6.0, **kw):
    return compute(BargeCapacityInputs(loa=100.0, beam=beam, depth=depth,
                                       cargo_type="bauxite", **kw))


# ---------- golden: headline worked examples ----------

def test_gas_golden_example():
    """RE-BASELINED 2026-09-18 by the DERIVED ARRANGEMENT (Niall).

    The cargo zone was bounded by fractions of LOA (10% fwd, 15% aft) that knew nothing
    about what had to fit in them. It is now built from the equipment and the gas code:

        fwd  = bow rake (1.6 x depth) + 0.50 m end-bulkhead space      =  10.10 m
        aft  = thruster room + 3 x 40 ft units + lifting wheelhouse
               + 2.00 m cofferdam/service to the cargo area             =  21.89 m

    so the cargo zone falls from 75.0 m to 68.0 m and gas capacity with it:
        was  1,669 t, draft 2.56 m, air draft (laden) 7.01 m
        now  1,497 t, draft 2.37 m, air draft (laden) 7.19 m   (-10.3% cargo)

    Updated 2026-09-18 (same day) when the unit mix went to THREE abreast -- the gas
    vessel carries a second ACCOMMODATION unit, the hopper a second BATTERY -- and the
    wheelhouse grew to 6.4 x 3.6 x 3.4 m. Three units abreast do not lengthen the block
    (they go across the beam); the wider, longer wheelhouse adds 0.60 m.
    The earlier figure was not wrong under its own assumption; it assumed the aft tank
    head could sit against the accommodation with no gas-code separation at all.

    The 2026-09-17 MAX_TANK_OD_M = 12 m rule still holds and still sets 2 tanks abreast.
    """
    r = _gas()
    assert r.phase == "liquid_gas"
    assert r.n_tanks_wide == 2
    assert abs(r.tank_outer_diameter_m - 6.50) < 0.05
    assert r.tank_outer_diameter_m <= 12.0 + 1e-9          # the rule itself
    assert abs(r.cargo_capacity_t - 1497) < 5
    assert abs(r.full_load_draft_m - 2.37) < 0.02
    assert abs(r.air_draft_m - 7.19) < 0.05
    assert abs(r.cargo_zone_length_m - 68.01) < 0.05
    assert r.ok and not r.overloaded


def test_bauxite_golden_example():
    """RE-BASELINED 2026-09-18 with the gas branch, for the same reason.

    The dry-bulk hold takes the same derived stern block (it carries the same battery,
    accommodation, thrusters and wheelhouse) but no gas-code separation -- only a 0.50 m
    end bulkhead each end. Cargo zone 75.0 m -> 69.5 m.
        was  5,083 t, draft 4.91 m, air draft (laden) 2.09 m
        now  4,711 t, draft 4.60 m, air draft (laden) 4.80 m   (-7.3% cargo)
    The air draft moves MOST: it used to be the hatch coaming, and the 40 ft units on the
    aft deck are taller than the coaming. The old figure was the wrong tallest point.
    """
    r = _bauxite()
    assert r.phase == "dry_bulk"
    assert abs(r.cargo_capacity_t - 4711) < 5
    assert abs(r.full_load_draft_m - 4.60) < 0.02
    assert abs(r.air_draft_m - 4.80) < 0.05
    assert abs(r.cargo_zone_length_m - 69.51) < 0.05
    assert r.ok and not r.overloaded


def test_arrangement_is_derived_not_a_fraction():
    """The end voids must come from the equipment, not from bow/stern_void_fraction."""
    r = _gas()
    a = r.aft_arrangement
    assert a is not None and r.separation is not None
    # aft void = the block + the gas-code separation, exactly
    assert abs(r.stern_void_length_m - (a.length_m + r.separation.aft_separation_m)) < 1e-9
    # fwd void = the bow rake + the forward end-bulkhead space, exactly
    assert abs(r.bow_void_length_m
               - (r.bow_rake_length_m + r.separation.fwd_separation_m)) < 1e-9
    # and it is NOT the old fraction
    assert abs(r.stern_void_length_m - 0.15 * 100.0) > 1.0


def test_bulk_and_gas_share_the_block_but_not_the_unit_mix():
    """One crew/propulsion arrangement, both vessels, so the block LENGTH is identical --
    the units sit ABREAST, so changing the mix moves the beam requirement, not the length.
    The mix itself differs: dry bulk takes a second BATTERY, gas a second ACCOMMODATION
    unit (Niall, 2026-09-18)."""
    g, b = _gas().aft_arrangement, _bauxite().aft_arrangement
    assert abs(g.length_m - b.length_m) < 1e-9
    assert abs(g.container_total_width_m - b.container_total_width_m) < 1e-9
    assert len(g.container_labels) == len(b.container_labels) == 3
    assert g.container_labels.count("ACCOM 40 FT") == 2
    assert b.container_labels.count("BATTERY 40 FT") == 2


def test_cargo_volume_is_inner_volume_times_fill():
    """The 95% is applied to the volume INSIDE the insulation and the steel, not the OD."""
    r = _gas()
    assert abs(r.cargo_volume_m3
               - r.containment_inner_volume_m3 * r.fill_ratio_applied) < 1e-6
    # the bore is the OD less twice the insulation and twice the wall
    expect = (r.tank_outer_diameter_m - 2 * r.insulation_thickness_mm / 1000.0
              - 2 * r.tank_wall_thickness_mm / 1000.0)
    assert abs(r.tank_inner_diameter_m - expect) < 1e-9
    assert r.tank_inner_diameter_m < r.tank_outer_diameter_m - 0.7   # insulation is real


def test_wider_cofferdam_costs_cargo():
    """The separation is a real length: widen it and the cargo zone shrinks by the same."""
    from vessel_designer.core.gas_separation import GasSeparationInputs
    base = _gas()
    wide = _gas(separation=GasSeparationInputs(opening_setback_m=4.0))
    assert abs((base.cargo_zone_length_m - wide.cargo_zone_length_m) - 2.0) < 1e-9
    assert wide.cargo_capacity_t < base.cargo_capacity_t


def test_navigating_air_draft_is_never_below_stowed():
    for r in (_gas(), _bauxite()):
        assert r.air_draft_navigating_light_m >= r.air_draft_light_m - 1e-9


# ---------- property: the physics that must always hold ----------

def test_gas_capacity_falls_slightly_with_depth():
    """CHANGED 2026-09-18. Gas tonnage used to be exactly flat in depth, because tank OD
    is set by beam and tank length by LOA. It now falls slightly, because the BOW RAKE is
    proportional to depth (1.6 x D) and the rake is inside the forward void. Deeper hull
    -> longer rake -> shorter cargo zone. Small, real, and worth seeing: if the rake rule
    is ever replaced by a surveyed length this coupling goes with it."""
    shallow, deep = _gas(depth=5.0), _gas(depth=6.0)
    assert deep.cargo_capacity_t < shallow.cargo_capacity_t
    assert abs(deep.bow_rake_length_m - shallow.bow_rake_length_m - 1.6) < 1e-9
    # the ONLY channel is the rake: same OD, same tank count
    assert deep.tank_outer_diameter_m == shallow.tank_outer_diameter_m
    assert (shallow.cargo_capacity_t - deep.cargo_capacity_t) / shallow.cargo_capacity_t < 0.05


def test_bulk_capacity_grows_with_depth():
    # Taller hull -> taller hold -> more volume.
    assert (_bauxite(depth=6.0).cargo_capacity_t
            > _bauxite(depth=5.0).cargo_capacity_t
            > _bauxite(depth=4.0).cargo_capacity_t)


def test_bauxite_denser_than_gas_per_metre_draft():
    # At equal hull, dense cargo sits deeper for its volume.
    assert _bauxite().cargo_capacity_t > _gas().cargo_capacity_t


def test_capacity_scales_faster_than_loa():
    """CHANGED 2026-09-18. Capacity used to be ~linear in LOA because the end voids were
    PERCENTAGES of LOA. They are now fixed lengths -- a wheelhouse and two 40 ft units do
    not double when the ship does -- so doubling LOA MORE than doubles the cargo. That is
    the real economics of a longer hull, and the old fraction hid it."""
    short = compute(BargeCapacityInputs(loa=100.0, beam=16.0, depth=6.0, cargo_type="bauxite"))
    long = compute(BargeCapacityInputs(loa=200.0, beam=16.0, depth=6.0, cargo_type="bauxite"))
    assert abs(short.stern_void_length_m - long.stern_void_length_m) < 1e-9   # fixed
    ratio = long.cargo_capacity_t / short.cargo_capacity_t
    assert 2.1 < ratio < 2.6
    # and the cargo zone is exactly LOA minus the two fixed voids
    assert abs(long.cargo_zone_length_m - short.cargo_zone_length_m - 100.0) < 1e-9


# ---------- checks: feasibility gating ----------

def test_overload_flagged_when_too_shallow():
    # Full gas tanks can't float in a 2 m hull -> overloaded, freeboard at the gunwale.
    # Was depth=4.0 until the 12 m tank-OD rule (2026-09-17) halved gas capacity; a 4 m
    # hull now floats it comfortably at 2.48 m, so the case had to move deeper to still
    # exercise the check.
    r = _gas(depth=2.0)
    assert r.overloaded
    assert not r.ok
    assert r.full_load_draft_m <= 2.0 + 1e-6


def test_wing_void_widens_cuts_bulk_volume():
    narrow = _bauxite()                                     # 1.0 m default
    wide = _bauxite(wing_void_width=3.0)
    assert wide.cargo_capacity_t < narrow.cargo_capacity_t


# ---------- bulk intact stability (GM) ----------

def test_bulk_gm_computed_and_positive():
    r = _bauxite()
    assert r.gm_m is not None and r.gm_m > 0.15
    assert any(c.name == "gm_positive" for c in r.checks)


def test_gm_grows_with_beam():
    # wider hull -> larger waterplane inertia -> larger BM -> larger GM
    assert _bauxite(beam=20.0).gm_m > _bauxite(beam=16.0).gm_m > _bauxite(beam=12.0).gm_m


def test_gas_has_no_bulk_gm():
    assert _gas().gm_m is None         # gas uses hydrostatics.calculate_stability, not this


# ---------- light / ballast air draft (added 2026-09-16) ----------
# An EMPTY barge floats high, so its air draft is the LARGEST. Bridge clearance must be
# gated on that, never on the laden figure, which is the favourable case.

def test_light_air_draft_exceeds_laden_gas():
    r = _gas()
    assert r.air_draft_light_m > r.air_draft_m
    assert r.light_draft_m < r.full_load_draft_m


def test_light_air_draft_exceeds_laden_bulk():
    r = _bauxite()
    assert r.air_draft_light_m > r.air_draft_m
    assert r.light_draft_m < r.full_load_draft_m


def test_air_draft_identity_holds_in_both_conditions():
    # air draft = top-above-keel - draft, in whichever condition.
    for r in (_gas(), _bauxite()):
        assert abs(r.air_draft_m - (r.air_draft_top_above_keel_m - r.full_load_draft_m)) < 1e-6
        assert abs(r.air_draft_light_m - (r.air_draft_top_above_keel_m - r.light_draft_m)) < 1e-6


def test_no_limit_means_no_air_draft_check():
    assert not any(c.name == "air_draft_within_limit" for c in _gas().checks)


def test_air_draft_check_gates_on_light_not_laden():
    # A limit BETWEEN the laden and light figures must FAIL: gating on laden would pass it.
    r0 = _gas()
    between = (r0.air_draft_m + r0.air_draft_light_m) / 2.0
    r = _gas(air_draft_limit_m=between)
    chk = next(c for c in r.checks if c.name == "air_draft_within_limit")
    assert not chk.ok and not r.ok


def test_air_draft_check_passes_when_light_clears():
    r = _gas(air_draft_limit_m=_gas().air_draft_light_m + 0.5)
    assert next(c for c in r.checks if c.name == "air_draft_within_limit").ok


def test_ballast_lowers_air_draft_monotonically():
    none = _gas(ballast_capacity_t=0.0)
    some = _gas(ballast_capacity_t=500.0)
    more = _gas(ballast_capacity_t=1500.0)
    assert none.air_draft_ballast_m == none.air_draft_light_m   # 0 ballast -> light
    assert more.air_draft_ballast_m < some.air_draft_ballast_m < none.air_draft_ballast_m
    assert more.ballast_draft_m > some.ballast_draft_m > none.ballast_draft_m


def test_ballast_can_rescue_a_failing_design():
    r0 = _gas()
    limit = (r0.air_draft_m + r0.air_draft_light_m) / 2.0
    assert not _gas(air_draft_limit_m=limit).ok                       # light fails it
    rescued = _gas(air_draft_limit_m=limit, ballast_capacity_t=3000.0)
    assert rescued.air_draft_ballast_m < rescued.air_draft_light_m
