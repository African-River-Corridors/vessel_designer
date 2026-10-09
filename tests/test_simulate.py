"""The web simulator's gas path goes through the arrangement search and hits the benchmarks."""
from vessel_designer.simulate import simulate

CN_II = dict(vessel="gas_barge", cargo="LPG_propane", loa_m=90, beam_m=14.8, depth_m=6.5, cb=0.85,
             freeboard_min_m=0.3, draught_limit_m=4.4, self_propelled=True, ruleset="IGC_2G",
             fill_ratio=0.95)


def test_gas_uses_the_search_not_auto():
    assert abs(simulate(CN_II)["results"]["cargo_t"] - 2058) < 1.0


def test_gas_optimised_depth_matches_snapshot():
    o = simulate(dict(CN_II, cargo="LNG", draught_limit_m=3.0, ruleset="IGC_2G_EXACT",
                      fill_ratio=None, optimise_depth=True))
    assert abs(o["results"]["cargo_t"] - 1738) < 1.0
    assert o["arrangement"]["fill_ratio"] == 0.98          # ruleset-driven default


def test_gas_stability_is_assessed_for_three_conditions():
    o = simulate(CN_II)
    assert [c["name"] for c in o["stability"]["conditions"]] == ["Laden", "Half laden", "Light"]
    assert o["stability"]["ok"]
    assert sum(c["name"].startswith("Stability") for c in o["checks"]) == 3


def test_tender_gas_barge_shows_failed_stability_checks():
    o = simulate(dict(CN_II, loa_m=60, beam_m=7.0, depth_m=6.0, draught_limit_m=None,
                      ruleset="IGC_2G_EXACT", fill_ratio=0.98, self_propelled=False))
    assert not o["stability"]["ok"]
    assert any(c["name"].startswith("Stability") and not c["ok"] for c in o["checks"])


def test_box_barge_unchanged():
    o = simulate(dict(vessel="box_barge", cargo="bauxite", loa_m=76.5, beam_m=11.4, depth_m=3.5,
                      cb=0.928, lightship_k_t_per_m3=0.1093, freeboard_min_m=0.3))
    assert 2200 < o["results"]["cargo_t"] < 2300


def test_gas_infeasible_fit_is_shown_as_a_failed_check(monkeypatch):
    """Issue #6: when fit() finds no passing arrangement, the page says so, not just the tonnage."""
    from dataclasses import replace
    import vessel_designer.simulate as sim
    real = sim.gas_fit
    monkeypatch.setattr(sim, "gas_fit", lambda *a, **k: replace(real(*a, **k), feasible=False))
    o = simulate(CN_II)
    assert o["arrangement"]["feasible"] is False
    assert any(c["name"] == "Feasible arrangement" and not c["ok"] for c in o["checks"])
    assert simulate(CN_II)["arrangement"]["feasible"] is False
    monkeypatch.undo()
    o = simulate(CN_II)
    assert o["arrangement"]["feasible"] is True
    assert not any(c["name"] == "Feasible arrangement" for c in o["checks"])
