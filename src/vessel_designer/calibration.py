"""Calibration pass: run Reference Vessel inputs through the core and compare with published figures.

    python -m vessel_designer.calibration      # writes calibration/results.md

The core is not tuned here. This module MEASURES the error; corrections are a separate,
deliberate step recorded as a calibrated factor with its evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute as capacity
from vessel_designer.core.resistance import (EnvironmentInputs, ResistanceInputs, TugInputs,
                                             compute as resistance)

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "calibration"
RHO_FRESH = 1.0
KMH_PER_KN = 1.852


# --- Independent lightship estimators (published, not ours) --------------------------------

def ls_padovezi(L: float, B: float, D: float) -> float:
    """Brazilian chata steel = lightship: 0.12 t/m3 x L.B.D (Padovezi 2003, USP thesis)."""
    return 0.12 * L * B * D


def ls_cn_draft(L: float, B: float, D: float, C: float = 0.128) -> float:
    """GB 38030.1 draft note (2018) §2.2.1: C.Lpp^1.4.B^0.75.D^0.4 (bulk C=0.128). Lpp ~ LOA here."""
    return C * L ** 1.4 * B ** 0.75 * D ** 0.4


def pct(model: float | None, obs: float | None) -> float | None:
    if model is None or obs in (None, 0):
        return None
    return 100.0 * (model - obs) / obs


def lbd(c: dict) -> float:
    return c["loa_m"] * c["beam_m"] * c["depth_m"]


def fit_factors(cases: list) -> dict:
    """Fit the barge factors from the cases. The fit IS the algorithm: re-run to regenerate.

    k (t/m3, lightship / L.B.D) per hold type: mean over cases with an observed lightship.
    Cb (box barges, on LOA): mean of (observed DWT + lightship) / (L.B.T.rho) over cases with
    a draught and DWT, not excluded; lightship = observed, else the fitted k.
    """
    k = {}
    for ht in sorted({c["hold_type"] for c in cases}):
        pts = [(c["id"], c["observed"]["lightship_t"] / lbd(c), c["confidence"])
               for c in cases if c["hold_type"] == ht and "lightship_t" in c["observed"]]
        if pts:
            vals = [v for _, v, _ in pts]
            k[ht] = {"value": round(sum(vals) / len(vals), 4), "min": round(min(vals), 4),
                     "max": round(max(vals), 4), "n": len(vals),
                     "evidence": [{"case": i, "k": round(v, 4), "confidence": cf} for i, v, cf in pts]}
    cb_pts = []
    for c in cases:
        o = c["observed"]
        if c["hold_type"] != "box" or not c.get("draught_m") or "dwt_t" not in o \
                or c.get("exclude_from_fit_cb"):
            continue
        ls = o.get("lightship_t", k["box"]["value"] * lbd(c))
        cb_pts.append((c["id"], (o["dwt_t"] + ls) / (c["loa_m"] * c["beam_m"] * c["draught_m"] * RHO_FRESH)))
    vals = [v for _, v in cb_pts]
    cb = {"value": round(sum(vals) / len(vals), 3), "min": round(min(vals), 3),
          "max": round(max(vals), 3), "n": len(vals),
          "evidence": [{"case": i, "cb": round(v, 3)} for i, v in cb_pts],
          "excluded": [{"case": c["id"], "why": c["exclude_from_fit_cb"]}
                       for c in cases if c.get("exclude_from_fit_cb")]}
    return {"lightship_k_t_per_m3": k, "block_coefficient_box_barge_on_loa": cb}


@dataclass
class BargeRow:
    case: dict
    ls_ported: float
    ls_cal: float
    ls_padovezi: float
    ls_cn: float
    dwt_ported: float | None = None
    dwt_cal: float | None = None
    ls_from_light_draught_cb1: float | None = None


def run_barge(c: dict, f: dict) -> BargeRow:
    L, B, D, T = c["loa_m"], c["beam_m"], c["depth_m"], c.get("draught_m")
    ported = capacity(BargeCapacityInputs(loa=L, beam=B, depth=D, cargo_type="bauxite",
                                          self_propelled=False))
    k = f["lightship_k_t_per_m3"][c["hold_type"]]["value"]
    cb = f["block_coefficient_box_barge_on_loa"]["value"]
    cal = capacity(BargeCapacityInputs(loa=L, beam=B, depth=D, cargo_type="bauxite",
                                       self_propelled=False, hold_type=c["hold_type"],
                                       lightship_k_t_per_m3=k, block_coefficient=cb))
    row = BargeRow(case=c, ls_ported=ported.lightship_t, ls_cal=cal.lightship_t,
                   ls_padovezi=ls_padovezi(L, B, D), ls_cn=ls_cn_draft(L, B, D))
    if T:
        row.dwt_ported = 0.85 * L * B * T * RHO_FRESH - ported.lightship_t
        row.dwt_cal = cb * L * B * T * RHO_FRESH - cal.lightship_t
    if "light_draught_m" in c["observed"]:
        row.ls_from_light_draught_cb1 = L * B * c["observed"]["light_draught_m"] * RHO_FRESH
    return row


@dataclass
class MotorRow:
    cargo: str
    loa: float
    boa: float
    T: float
    disp: float
    cargo_t: float
    power_kw: float
    speed_kmh: float
    cb_implied: float
    ls_plus_consumables: float
    delivered_kw: float | None


def run_motor(cargo: str, r: list, speed_kmh: float) -> MotorRow:
    loa, boa, T, disp, cargo_t, p = r
    cb = disp / (loa * boa * T * RHO_FRESH)   # on LOA: a lower bound on the true Cb (Lwl < LOA)
    v = speed_kmh / KMH_PER_KN
    deep = EnvironmentInputs(name="deep (calibration)", water_depth=50.0,
                             channel_width_bottom=1000.0, channel_width_surface=1000.0,
                             water_density=RHO_FRESH, is_deep_water=True, apply_squat_limit=False)
    ri = ResistanceInputs(loa=loa, lwl=0.97 * loa, beam=boa, draft=T, block_coefficient=min(cb / 0.97, 0.99),
                          displacement_tonnes=disp, tug=TugInputs(engine_power_kw=1e6),
                          environments=[deep], speed_min_knots=v, speed_max_knots=v + 0.05,  # core rounds speeds to 0.1 kn
                          speed_step_knots=1.0)
    pts = resistance(ri).environments[0].speed_curve
    delivered = pts[0].delivered_power_kw if pts else None
    return MotorRow(cargo, loa, boa, T, disp, cargo_t, p, speed_kmh, cb, disp - cargo_t, delivered)


def fmt(x, nd=0):
    return "–" if x is None else f"{x:,.{nd}f}"


def report() -> str:
    cases = yaml.safe_load((CAL / "cases.yaml").read_text())
    f = fit_factors(cases["dry_barge"])
    (CAL / "factors.yaml").write_text(
        "# GENERATED by python -m vessel_designer.calibration from calibration/cases.yaml.\n"
        "# Do not edit: add or correct cases, then re-run.\n"
        + yaml.safe_dump(f, sort_keys=False, width=110))
    rows = [run_barge(c, f) for c in cases["dry_barge"]]
    kb, cbf = f["lightship_k_t_per_m3"], f["block_coefficient_box_barge_on_loa"]
    out = ["<!-- GENERATED by python -m vessel_designer.calibration — do not edit -->",
           "# Calibration results", "",
           "*Ported* = core as ported from Ankobra (sloped-hopper build-up, Cb 0.85). "
           "*Calibrated* = hold-type k × L·B·D and the fitted Cb, from `factors.yaml`.", "",
           "## Fitted factors", ""]
    for ht, v in kb.items():
        out.append(f"- **k, {ht} hold:** {v['value']} t/m³ (range {v['min']}–{v['max']}, n = {v['n']})")
    out += [f"- **Cb, box barge on LOA:** {cbf['value']} (range {cbf['min']}–{cbf['max']}, n = {cbf['n']}; "
            f"{len(cbf['excluded'])} excluded — see factors.yaml)", "",
            "## 1. Push barges — lightship", "",
            "| Case | Hold | Conf. | Observed (t) | Ported | err % | Calibrated | err % | Padovezi 0.12 | err % | CN draft | err % |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c, o = r.case, r.case["observed"]
        obs = o.get("lightship_t")
        obs_txt = fmt(obs) if obs else (f"≤{fmt(r.ls_from_light_draught_cb1)} (light draught, Cb=1)"
                                        if r.ls_from_light_draught_cb1 else "–")
        out.append(f"| {c['id']} | {c['hold_type']} | {c['confidence']} | {obs_txt} | "
                   f"{fmt(r.ls_ported)} | {fmt(pct(r.ls_ported, obs), 1)} | {fmt(r.ls_cal)} | "
                   f"{fmt(pct(r.ls_cal, obs), 1)} | {fmt(r.ls_padovezi)} | {fmt(pct(r.ls_padovezi, obs), 1)} | "
                   f"{fmt(r.ls_cn)} | {fmt(pct(r.ls_cn, obs), 1)} |")
    out += ["", "Note: where a case is in the k fit, its calibrated error is in-sample.", "",
            "## 2. Push barges — deadweight at the stated draught", "",
            "| Case | T (m) | Observed DWT (t) | Ported | err % | Calibrated | err % | In Cb fit |",
            "|---|---|---|---|---|---|---|---|"]
    fit_ids = {e["case"] for e in cbf["evidence"]}
    for r in rows:
        c, o = r.case, r.case["observed"]
        if not c.get("draught_m"):
            continue
        infit = "yes" if c["id"] in fit_ids else ("excluded" if c.get("exclude_from_fit_cb") else "no")
        out.append(f"| {c['id']} | {c['draught_m']} | {fmt(o.get('dwt_t'))} | {fmt(r.dwt_ported)} | "
                   f"{fmt(pct(r.dwt_ported, o.get('dwt_t')), 1)} | {fmt(r.dwt_cal)} | "
                   f"{fmt(pct(r.dwt_cal, o.get('dwt_t')), 1)} | {infit} |")

    src = yaml.safe_load((CAL / "cn_yangtze_gb38030_draft_2018.yaml").read_text())
    mrows = []
    for cargo in ("bulk", "liquid"):
        dp = src["design_points"][cargo]
        mrows += [run_motor(cargo, r, dp["speed_kmh"]) for r in dp["rows"]]
    out += ["", "## 3. Yangtze motor vessels — GB 38030 draft design points (2018)", "",
            "Design-study points, not built ships. Cb implied on LOA (a lower bound). "
            "Delivered power = core `resistance`, deep water, Lwl = 0.97·LOA. "
            "Ratio = installed main power ÷ delivered power.", "",
            "| Cargo | LOA×B×T | Δ (t) | Cargo (t) | Δ − cargo (t) | Implied Cb | Speed (km/h) | "
            "Installed (kW) | Delivered (kW) | Ratio |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for m in mrows:
        ratio = m.power_kw / m.delivered_kw if m.delivered_kw else None
        out.append(f"| {m.cargo} | {m.loa:g}×{m.boa:g}×{m.T:g} | {fmt(m.disp)} | {fmt(m.cargo_t)} | "
                   f"{fmt(m.ls_plus_consumables)} | {m.cb_implied:.3f} | {m.speed_kmh:g} | "
                   f"{fmt(m.power_kw)} | {fmt(m.delivered_kw)} | {fmt(ratio, 2)} |")
    return "\n".join(out) + "\n"


def main() -> None:
    (CAL / "results.md").write_text(report())
    print((CAL / "results.md").read_text())


if __name__ == "__main__":
    main()
