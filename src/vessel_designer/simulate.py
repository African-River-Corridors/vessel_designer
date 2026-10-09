"""One-call barge simulation for the web simulator (runs in the browser via Pyodide).

    simulate(params: dict) -> dict      # JSON in, JSON out

Adds the weight limit the core leaves out: the core sizes cargo by HOLD VOLUME; a real barge
also stops at its draught limit. Cargo = the smaller of the two, and the result says which
governed. Pushed barges only for now; the pusher is a separate vessel and is not included.
Pure calculation, no I/O.
"""
from __future__ import annotations

from dataclasses import asdict

from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute as capacity
from vessel_designer.core.cargo import CARGO_DATABASE
from vessel_designer.core.gas_arrangement import DEFAULT_DEPTHS_M, RULESETS, fit as gas_fit
from vessel_designer.core.gas_stability import assess as assess_stability, criteria_set_for
from vessel_designer.core.resistance import (EnvironmentInputs, ResistanceInputs, TugInputs,
                                             compute as resistance)

RHO = 1.0  # fresh water, t/m3
# Tank filling limit by ruleset (defect 7): IGC 15.3 default 98 %, ADN 95 %.
FILL_BY_RULESET = {"IGC_2G": 0.98, "IGC_2G_EXACT": 0.98, "ADN_G": 0.95}

VESSELS = {
    # id: (label, hold_type for the core, allowed cargo phases)
    "box_barge": ("Box-hold dry bulk barge", "box", {"dry_bulk"}),
    "hopper_barge": ("Sloped-hopper dry bulk barge", "sloped_hopper", {"dry_bulk"}),
    "gas_barge": ("Gas barge, IMO Type C tanks", None, {"liquid_gas"}),
}


def cargo_options() -> list[dict]:
    return [{"id": k, "name": v.name, "phase": v.phase, "density_kg_m3": v.density}
            for k, v in CARGO_DATABASE.items()]


def _env(name, depth, bottom_w, slope, current_kn=0.0, deep=False):
    surface = bottom_w + 2.0 * slope * depth
    return EnvironmentInputs(name=name, water_depth=depth, channel_width_bottom=bottom_w,
                             channel_width_surface=surface, bank_slope=slope,
                             current_speed_knots=current_kn, water_density=RHO,
                             is_deep_water=deep, apply_squat_limit=not deep)


def simulate(p: dict) -> dict:
    vessel = p.get("vessel", "box_barge")
    label, hold_type, phases = VESSELS[vessel]
    cargo = CARGO_DATABASE[p["cargo"]]
    if cargo.phase not in phases:
        return {"error": f"{cargo.name} cannot be carried in a {label.lower()}."}
    L, B, D = float(p["loa_m"]), float(p["beam_m"]), float(p["depth_m"])
    cb = float(p["cb"])
    self_propelled = bool(p.get("self_propelled", False))
    if vessel == "gas_barge":
        return _simulate_gas(p, label, cargo, L, B, D, cb, self_propelled)
    kw = dict(loa=L, beam=B, depth=D, cargo_type=p["cargo"], self_propelled=self_propelled,
              block_coefficient=cb, required_freeboard=float(p.get("freeboard_min_m", 0.3)),
              air_draft_limit_m=p.get("air_draft_limit_m"))
    if hold_type:
        kw["hold_type"] = hold_type
        if hold_type != "sloped_hopper":
            kw["lightship_k_t_per_m3"] = float(p["lightship_k_t_per_m3"])
    try:
        r = capacity(BargeCapacityInputs(**kw))
    except ValueError as exc:
        return {"error": str(exc)}

    # --- Draught limit and the weight-bound cargo -----------------------------------------
    ch = p.get("channel") or {}
    limits = {"Hull (depth − min. freeboard)": D - kw["required_freeboard"]}
    if p.get("draught_limit_m"):
        limits["Draught limit"] = float(p["draught_limit_m"])
    if ch.get("depth_m"):
        limits["Channel (depth − under-keel clearance)"] = float(ch["depth_m"]) - float(ch.get("ukc_m", 0.5))
    lim_name, t_max = min(limits.items(), key=lambda kv: kv[1])
    ls = r.lightship_t
    disp_max = cb * L * B * t_max * RHO
    cargo_weight_bound = max(0.0, disp_max - ls)
    cargo_volume_bound = r.cargo_capacity_t
    cargo_t = min(cargo_volume_bound, cargo_weight_bound)
    governs = "hold volume" if cargo_volume_bound <= cargo_weight_bound else f"draught — {lim_name}"
    disp = ls + cargo_t
    T = disp / (cb * L * B * RHO)
    h_top = r.air_draft_top_above_keel_m

    checks = [{"name": "Cargo > 0", "ok": cargo_t > 0,
               "message": "Lightship alone exceeds the allowed draught." if cargo_t <= 0 else "OK"}]
    for c in r.checks:
        if c.name in ("not_overloaded", "freeboard_ok"):
            continue  # superseded: the simulator loads to the draught limit, not to a full hold
        checks.append({"name": c.name.replace("_", " "), "ok": c.ok, "message": c.message,
                       "severity": c.severity})
    if p.get("air_draft_limit_m"):
        ok = r.air_draft_light_m <= float(p["air_draft_limit_m"])
        checks.append({"name": "Air draft (empty, governing)", "ok": ok,
                       "message": f"{r.air_draft_light_m:.2f} m vs limit {float(p['air_draft_limit_m']):.2f} m"})

    curves = _curves(p, L, B, T, cb, disp)

    geo = {k: getattr(r, k) for k in (
        "bow_void_length_m", "stern_void_length_m", "cargo_zone_length_m", "bow_rake_length_m",
        "tank_outer_diameter_m", "n_tanks_wide", "n_tanks_total", "side_clearance_m",
        "bottom_clearance_m", "hold_height_m", "hold_top_width_m", "hold_bottom_width_m",
        "insulation_thickness_mm")}
    return {
        "vessel": label, "cargo": cargo.name, "phase": cargo.phase,
        "self_propelled": self_propelled, "arrangement": None,
        "dims": {"loa_m": L, "beam_m": B, "depth_m": D, "cb": cb},
        "geometry": geo,
        "results": {
            "cargo_t": cargo_t, "cargo_volume_bound_t": cargo_volume_bound,
            "cargo_weight_bound_t": cargo_weight_bound, "governs": governs,
            "cargo_volume_m3": r.cargo_volume_m3, "lightship_t": ls, "displacement_t": disp,
            "deadweight_t": disp - ls, "draught_m": T, "draught_max_m": t_max,
            "freeboard_m": D - T, "light_draught_m": r.light_draft_m,
            "air_draft_loaded_m": h_top - T, "air_draft_light_m": r.air_draft_light_m,
            "h_over_T": (float(ch["depth_m"]) / T) if ch.get("depth_m") and T > 0 else None,
        },
        "checks": checks, "warnings": list(r.warnings), "curves": curves,
    }


def _curves(p: dict, L: float, B: float, T: float, cb: float, disp: float) -> list:
    """Speed–power for this hull alone (a pusher's hull and propulsor are not modelled)."""
    ch = p.get("channel") or {}
    envs = [_env("Deep water", 50.0, 1000.0, 3.0, deep=True)]
    if ch.get("depth_m") and ch.get("bottom_width_m"):
        envs.insert(0, _env("Channel", float(ch["depth_m"]), float(ch["bottom_width_m"]),
                            float(ch.get("bank_slope", 3.0)), float(ch.get("current_kn", 0.0))))
    if T <= 0:
        return []
    rr = resistance(ResistanceInputs(
        loa=L, lwl=L, beam=B, draft=T, block_coefficient=cb, displacement_tonnes=disp,
        tug=TugInputs(engine_power_kw=1e6, propulsive_efficiency=float(p.get("eta_d", 0.45))),
        environments=envs, speed_min_knots=1.0, speed_max_knots=float(p.get("speed_max_kn", 10.0)),
        speed_step_knots=0.5))
    return [{"name": e.name, "limiting_speed_kn": e.limiting_speed_knots, "blockage": e.blockage_ratio,
             "points": [{"kn": s.speed_knots, "kw": s.delivered_power_kw, "fuel_lph": s.fuel_litres_per_hour,
                         "squat_m": s.squat_m, "squat_limited": s.squat_limited} for s in e.speed_curve]}
            for e in rr.environments]


def _simulate_gas(p, label, cargo, L, B, D, cb, self_propelled) -> dict:
    """Gas barges go through the arrangement SEARCH (core.gas_arrangement.fit), never the
    single AUTO arrangement -- AUTO can land on the worse of two roots (defect 1)."""
    ruleset = p.get("ruleset", "IGC_2G_EXACT")
    if ruleset not in RULESETS:
        return {"error": f"Unknown ruleset {ruleset!r}."}
    fill = float(p.get("fill_ratio") or FILL_BY_RULESET[ruleset])
    fb = float(p.get("freeboard_min_m", 0.3))
    ch = p.get("channel") or {}
    limits = {}
    if p.get("draught_limit_m"):
        limits["Draught limit"] = float(p["draught_limit_m"])
    if ch.get("depth_m"):
        limits["Channel (depth − under-keel clearance)"] = float(ch["depth_m"]) - float(ch.get("ukc_m", 0.5))
    if p.get("optimise_depth"):
        cap = min(limits.values()) if limits else None
        depths = [d for d in DEFAULT_DEPTHS_M if cap is None or d - fb >= cap] or [DEFAULT_DEPTHS_M[-1]]
    else:
        depths = [D]
        limits["Hull (depth − min. freeboard)"] = D - fb
    if not limits:     # optimising depth with no waterway limit: let the deepest hull set it
        limits["Hull (depth − min. freeboard)"] = depths[-1] - fb
    lim_name, t_max = min(limits.items(), key=lambda kv: kv[1])
    f = gas_fit(L, B, p["cargo"], t_max, ruleset=ruleset, fill_ratio=fill,
                self_propelled=self_propelled, depths=depths, block_coefficient=cb,
                adn_tank_cap_m3=float(p.get("adn_tank_cap_m3", 1000.0)))
    r = f.engine_result
    D = f.depth_m
    T = f.draft_at_payload_m if f.payload_t > 0 else (r.light_draft_m or 0.0)
    disp = r.lightship_t + f.payload_t
    governs = {"volume": "tank volume", "draft": f"draught — {lim_name}",
               "no cargo area": "no cargo area (hull shorter than its fixed end spaces)"}[f.binding]
    checks = [{"name": "Cargo > 0", "ok": f.payload_t > 0,
               "message": "OK" if f.payload_t > 0 else "Nothing fits: lengthen or widen the hull."}]
    if f.payload_t > 0 and not f.feasible:
        # fit() found no arrangement that passes its error checks and returned the best failing
        # one; say so up front, the failing checks themselves follow below.
        checks.append({"name": "Feasible arrangement", "ok": False,
                       "message": "No tank arrangement passes its checks on this hull; the best "
                                  "failing one is shown. See the failed checks."})
    for c in r.checks:
        if c.name in ("not_overloaded", "freeboard_ok"):
            continue
        checks.append({"name": c.name.replace("_", " "), "ok": c.ok, "message": c.message,
                       "severity": c.severity})
    for msg in f.failed_checks:
        if msg.startswith("adn_wide_tank"):
            checks.append({"name": "ADN wide tank", "ok": False, "message": msg.split(": ", 1)[1],
                           "severity": "warning"})
    if p.get("air_draft_limit_m"):
        ok = r.air_draft_light_m <= float(p["air_draft_limit_m"])
        checks.append({"name": "Air draft (empty, governing)", "ok": ok,
                       "message": f"{r.air_draft_light_m:.2f} m vs limit {float(p['air_draft_limit_m']):.2f} m"})
    stability = None
    if f.payload_t > 0 and r.gas_basis:
        a = assess_stability(r, f.payload_t, block_coefficient=cb,
                             criteria_set=criteria_set_for(ruleset))
        for c in a.conditions:
            bad = [x for x in c.criteria if not x.ok]
            checks.append({"name": f"Stability — {c.name.lower()}", "ok": not bad,
                           "message": (f"GM {c.gm_fluid_m:.2f} m (fluid), max GZ {c.max_gz_m:.2f} m at "
                                       f"{c.max_gz_deg:.0f}°" + ("" if not bad else " — fails: " +
                                       ", ".join(f"{x.name} {x.value:.3f} < {x.limit}" for x in bad)))})
        stability = {
            "criteria_set": {"IS_CODE_2008": "IMO IS Code 2008, Part A 2.2",
                             "ADN_9_3_1_14_2": "ADN 2025 9.3.1.14"}[a.criteria_set],
            "ok": a.ok, "governing": a.governing.name, "limitations": a.limitations,
            "conditions": [{
                "name": c.name, "cargo_t": c.cargo_t, "fill": c.fill_fraction,
                "displacement_t": c.displacement_t, "draught_m": c.draught_m, "kg_m": c.kg_m,
                "gm_solid_m": c.gm_solid_m, "free_surface_m": c.free_surface_m,
                "gm_fluid_m": c.gm_fluid_m, "max_gz_m": c.max_gz_m, "max_gz_deg": c.max_gz_deg,
                "deck_edge_deg": c.deck_edge_deg, "gz": c.gz,
                "criteria": [{"name": x.name, "value": x.value, "limit": x.limit, "ok": x.ok,
                              "source": x.source} for x in c.criteria]} for c in a.conditions]}
    geo = {k: getattr(r, k) for k in (
        "bow_void_length_m", "stern_void_length_m", "cargo_zone_length_m", "bow_rake_length_m",
        "tank_outer_diameter_m", "n_tanks_wide", "n_tanks_total", "side_clearance_m",
        "bottom_clearance_m", "insulation_thickness_mm")}
    return {
        "vessel": label, "cargo": cargo.name, "phase": cargo.phase, "self_propelled": self_propelled,
        "dims": {"loa_m": L, "beam_m": B, "depth_m": D, "cb": cb},
        "geometry": geo,
        "arrangement": {"ruleset": ruleset, "fill_ratio": fill, "n_wide": f.n_tanks_wide,
                        "n_long": f.n_tanks_long, "tank_od_m": f.tank_od_m,
                        "per_tank_m3": f.per_tank_volume_m3, "side_clearance_m": f.side_clearance_m,
                        "depth_m": f.depth_m, "depth_optimised": bool(p.get("optimise_depth")),
                        "candidates_tried": f.candidates_tried, "feasible": f.feasible},
        "results": {
            "cargo_t": f.payload_t, "cargo_volume_bound_t": f.volume_capacity_t,
            "cargo_weight_bound_t": max(0.0, cb * L * B * t_max * RHO - r.lightship_t),
            "governs": governs, "cargo_volume_m3": r.cargo_volume_m3, "lightship_t": r.lightship_t,
            "displacement_t": disp, "deadweight_t": f.payload_t, "draught_m": T,
            "draught_max_m": t_max, "freeboard_m": D - T, "light_draught_m": r.light_draft_m,
            "air_draft_loaded_m": r.air_draft_top_above_keel_m - T,
            "air_draft_light_m": r.air_draft_light_m,
            "h_over_T": (float(ch["depth_m"]) / T) if ch.get("depth_m") and T > 0 else None,
        },
        "checks": checks, "warnings": list(r.warnings), "curves": _curves(p, L, B, T, cb, disp),
        "stability": stability,
    }
