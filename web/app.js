/* Barge Design Simulator — UI. All engineering runs in Python (vessel_designer.simulate) via Pyodide. */
"use strict";

const $ = (s) => document.querySelector(s);
const form = $("#inputs");
let py = null, runPy = null, CLASSES = [], FACTORS = null, CARGOES = [];

const CORE_DEFAULT_CB = 0.85;          // the ported core's default, used where no fit exists
const fmt = (x, d = 0) => (x == null || Number.isNaN(x)) ? "–" :
  Number(x).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
const svgEl = (tag, attrs = {}, text) => {
  const a = Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(" ");
  return text == null ? `<${tag} ${a}/>` : `<${tag} ${a}>${text}</${tag}>`;
};
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

async function boot() {
  try {
    const [classes, factors, build] = await Promise.all(
      ["data/classes.json", "data/factors.json", "data/build.json"].map((u) => fetch(u).then((r) => r.json())));
    CLASSES = classes; FACTORS = factors;
    py = await loadPyodide();
    await py.loadPackage(["numpy", "micropip"]);
    const wheel = new URL(`wheels/${build.wheel}`, location.href).href;
    await py.pyimport("micropip").install(wheel, { deps: false });
    py.runPython(`
import json
from vessel_designer.simulate import simulate, cargo_options
def run(js): return json.dumps(simulate(json.loads(js)))
def cargoes(): return json.dumps(cargo_options())
`);
    runPy = py.globals.get("run");
    CARGOES = JSON.parse(py.globals.get("cargoes")());
    initForm();
    $("#status").classList.add("ok");
    update();
  } catch (e) {
    console.error(e);
    $("#status").textContent = "The calculation engine failed to load: " + e.message;
    $("#status").classList.add("err");
  }
}

function initForm() {
  form.k.value = FACTORS.box_k.value;
  const std = form.std;
  const groups = {};
  CLASSES.filter((c) => c.formation === "pushed_barge").forEach((c) => (groups[c.family] ||= []).push(c));
  Object.entries(groups).forEach(([fam, list]) => {
    const og = document.createElement("optgroup"); og.label = fam;
    list.forEach((c) => {
      const o = document.createElement("option"); o.value = c.id;
      o.textContent = `${c.id} — ${fmt(c.loa_m[1], 1)} × ${fmt(c.beam_m[1], 1)} m`;
      og.appendChild(o);
    });
    std.appendChild(og);
  });
  fillCargo();
  form.vessel.addEventListener("change", () => { fillCargo(); setDefaultCb(); showGas(); update(); });
  form.ruleset.addEventListener("change", () => { form.fill_ratio.value = form.ruleset.value === "ADN_G" ? 0.95 : 0.98; update(); });
  showGas();
  std.addEventListener("change", () => { applyClass(std.value); update(); });
  let t; form.addEventListener("input", (e) => {
    if (["std", "vessel", "ruleset"].includes(e.target.name)) return;
    if (e.target.name === "optimise_depth") showGas();
    clearTimeout(t); t = setTimeout(update, 120);
  });
}

function fillCargo() {
  const phase = form.vessel.value === "gas_barge" ? "liquid_gas" : "dry_bulk";
  const prev = form.cargo.value;
  form.cargo.innerHTML = CARGOES.filter((c) => c.phase === phase)
    .map((c) => `<option value="${c.id}">${c.name} (${fmt(c.density_kg_m3)} kg/m³)</option>`).join("");
  if ([...form.cargo.options].some((o) => o.value === prev)) form.cargo.value = prev;
}

function showGas() {
  const gas = form.vessel.value === "gas_barge";
  $("#gasopts").hidden = !gas;
  form.depth_m.disabled = gas && form.optimise_depth.checked;
  form.depth_m.closest("label").title = form.depth_m.disabled ? "Set by 'Find the best moulded depth'" : "";
}

function setDefaultCb() {
  form.cb.value = form.vessel.value === "box_barge" ? FACTORS.box_cb.value : CORE_DEFAULT_CB;
}

function applyClass(id) {
  const c = CLASSES.find((x) => x.id === id);
  if (!c) return;
  form.loa_m.value = c.loa_m[1];
  form.beam_m.value = c.beam_m[1];
  form.draught_limit_m.value = c.draught_m ? c.draught_m[1] : "";
}

function params() {
  const v = (n) => form[n].value === "" ? null : Number(form[n].value);
  return {
    vessel: form.vessel.value, cargo: form.cargo.value, self_propelled: form.self_propelled.value === "1",
    ruleset: form.ruleset.value, fill_ratio: v("fill_ratio"), adn_tank_cap_m3: v("adn_tank_cap_m3"),
    optimise_depth: form.optimise_depth.checked,
    loa_m: v("loa_m"), beam_m: v("beam_m"), depth_m: v("depth_m"), cb: v("cb"),
    freeboard_min_m: v("freeboard_min_m") ?? 0, draught_limit_m: v("draught_limit_m"),
    air_draft_limit_m: v("air_draft_limit_m"), lightship_k_t_per_m3: v("k"), eta_d: v("eta_d"),
    channel: { depth_m: v("ch_depth"), bottom_width_m: v("ch_width"), bank_slope: v("ch_slope") ?? 3,
               ukc_m: v("ch_ukc") ?? 0, current_kn: v("ch_current") ?? 0 },
  };
}

function update() {
  if (!runPy) return;
  const p = params();
  let r;
  try { r = JSON.parse(runPy(JSON.stringify(p))); }
  catch (e) { r = { error: String(e.message || e).split("\n").slice(-2).join(" ") }; }
  if (r.error) {
    $("#kpis").innerHTML = `<p class="err-msg">${r.error}</p>`;
    ["#governs", "#drawing", "#chart", "#checks", "#warnings"].forEach((s) => ($(s).innerHTML = ""));
    return;
  }
  renderKpis(r); renderCalib(p); renderDrawing(r); renderChart(r); renderStability(r); renderChecks(r); renderMatches(p);
}

function renderKpis(r) {
  const x = r.results;
  const tiles = [
    ["Cargo", `${fmt(x.cargo_t)} t`, true], ["Draught", `${fmt(x.draught_m, 2)} m`],
    ["Freeboard", `${fmt(x.freeboard_m, 2)} m`], ["Lightship", `${fmt(x.lightship_t)} t`],
    ["Displacement", `${fmt(x.displacement_t)} t`], ["Hold / tank volume", `${fmt(x.cargo_volume_m3)} m³`],
    ["Air draft, empty", `${fmt(x.air_draft_light_m, 2)} m`],
    ["Water depth / draught", x.h_over_T ? fmt(x.h_over_T, 2) : "–"],
  ];
  if (r.arrangement) tiles.splice(2, 1, ["Moulded depth" + (r.arrangement.depth_optimised ? " (best)" : ""), `${fmt(r.dims.depth_m, 2)} m`]);
  $("#kpis").innerHTML = tiles.map(([k, v, big]) =>
    `<div class="kpi${big ? " big" : ""}"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
  const other = x.governs === "hold volume"
    ? `the draught would allow ${fmt(x.cargo_weight_bound_t)} t`
    : `the ${r.arrangement ? "tanks" : "hold"} would take ${fmt(x.cargo_volume_bound_t)} t`;
  $("#governs").textContent = `Cargo is limited by ${x.governs} — ${other}.`;
}

function renderCalib(p) {
  const el = $("#calib");
  if (p.vessel === "box_barge") {
    const k = FACTORS.box_k, cb = FACTORS.box_cb;
    el.className = "calib good";
    el.innerHTML = `<b>Calibration:</b> lightship factor ${k.value} t/m³ fitted on ${k.n} published barges ` +
      `(range ${k.min}–${k.max}); block coefficient ${cb.value} on ${cb.n} barges. ` +
      `On those barges: lightship within −11 % to +15 %, deadweight within −8 % to +6 % (in-sample).`;
  } else if (p.vessel === "gas_barge") {
    el.className = "calib warn";
    el.innerHTML = `<b>Arrangement checked, weights not yet calibrated.</b> The tank search reproduces the ` +
      `engine's own benchmarks to within 1 t, but those are model results. Lightship has not yet been ` +
      `checked against built gas barges. Stability is a concept-stage intact check — see Intact stability.`;
  } else {
    el.className = "calib warn";
    el.innerHTML = `<b>Not yet calibrated.</b> This barge type still uses the earlier concept method. On box barges that method overstated lightship by 30–110 %, so treat cargo ` +
      `figures here as conservative until real ${p.vessel === "gas_barge" ? "gas barges" : "hopper barges"} are added.`;
  }
}

/* ---------- Drawing: profile (vertical ×2), plan and midship section ---------- */
function renderDrawing(r) {
  const { loa_m: L, beam_m: B, depth_m: D } = r.dims, g = r.geometry, x = r.results;
  const W = 900, pad = 24, sx = (W - 2 * pad - 50) / L, vx = 2;
  const gas = r.phase === "liquid_gas";
  const navy = css("--navy"), gold = css("--gold"), water = css("--water"), steel = css("--steel");
  const above = gas ? Math.max(0, (g.bottom_clearance_m || 0) + (g.tank_outer_diameter_m || 0) - D) : 1.0;
  let s = "";

  // PROFILE
  const pH = (D + above + 0.6) * sx * vx, y0 = 30 + (above + 0.3) * sx * vx;   // y0 = deck line
  const yk = y0 + D * sx * vx, X = (m) => pad + m * sx, Yp = (m) => yk - m * sx * vx;
  const rake = g.bow_rake_length_m || 0;
  s += svgEl("text", { x: pad, y: 18, "font-size": 12, fill: gold, "font-weight": 700, "letter-spacing": "1" }, "PROFILE  (vertical scale ×2)");
  const hullPts = `${X(0)},${Yp(D)} ${X(L)},${Yp(D)} ${X(L)},${Yp(D * 0.8)} ${X(L - rake)},${Yp(0)} ${X(0)},${Yp(0)}`;
  s += svgEl("polygon", { points: hullPts, fill: "#fff" });
  const z0 = g.stern_void_length_m, z1 = L - g.bow_void_length_m;
  if (gas && g.n_tanks_total) {
    const nl = r.arrangement ? r.arrangement.n_long : Math.round(g.n_tanks_total / (g.n_tanks_wide || 1)), gap = 0.6;
    const tl = (z1 - z0 - gap * (nl - 1)) / nl, od = g.tank_outer_diameter_m, zb = g.bottom_clearance_m || 0.5;
    for (let i = 0; i < nl; i++) {
      const a = z0 + i * (tl + gap);
      s += svgEl("rect", { x: X(a), y: Yp(zb + od), width: tl * sx, height: od * sx * vx, rx: Math.min(od * sx / 2, tl * sx / 2), fill: gold, opacity: 0.35, stroke: gold });
    }
  } else {
    const db = D + 1.0 - (g.hold_height_m || D);
    s += svgEl("rect", { x: X(z0), y: Yp(D + 1.0), width: (z1 - z0) * sx, height: (D + 1.0 - db) * sx * vx, fill: gold, opacity: 0.25, stroke: gold });
  }
  s += svgEl("rect", { x: X(0) - 6, y: Yp(x.draught_m), width: L * sx + 12, height: x.draught_m * sx * vx + 6, fill: water, opacity: 0.55 });
  s += svgEl("polygon", { points: hullPts, fill: "none", stroke: navy, "stroke-width": 2 });
  if (r.self_propelled && z0 > 0) {
    s += svgEl("rect", { x: X(0), y: Yp(D + 2.5), width: Math.min(z0, 12) * sx, height: 2.5 * sx * vx, fill: "none", stroke: navy, "stroke-dasharray": "3 2" });
    s += svgEl("text", { x: X(z0 / 2), y: Yp(D / 2) + 4, "font-size": 10, fill: css("--muted"), "text-anchor": "middle" }, "machinery · accommodation");
  }
  s += svgEl("line", { x1: X(0) - 6, x2: X(L) + 6, y1: Yp(x.draught_m), y2: Yp(x.draught_m), stroke: "#3A7CA5", "stroke-width": 1.5 });
  s += svgEl("text", { x: X(L) - 4, y: Yp(x.draught_m) - 4, "font-size": 11, fill: "#3A7CA5", "text-anchor": "end" }, `T = ${fmt(x.draught_m, 2)} m`);
  s += svgEl("text", { x: X(0), y: yk + 16, "font-size": 11, fill: css("--muted") }, "Stern");
  s += svgEl("text", { x: X(L), y: yk + 16, "font-size": 11, fill: css("--muted"), "text-anchor": "end" }, `Bow · LOA ${fmt(L, 1)} m`);

  // PLAN
  const py0 = yk + 46, Y = (m) => py0 + m * sx;
  s += svgEl("text", { x: pad, y: py0 - 8, "font-size": 12, fill: gold, "font-weight": 700, "letter-spacing": "1" }, "PLAN");
  s += svgEl("rect", { x: X(0), y: Y(0), width: L * sx, height: B * sx, fill: "none", stroke: navy, "stroke-width": 2 });
  if (gas && g.n_tanks_total) {
    const nw = g.n_tanks_wide || 1, nl = r.arrangement ? r.arrangement.n_long : Math.round(g.n_tanks_total / nw), gap = 0.6, od = g.tank_outer_diameter_m;
    const tl = (z1 - z0 - gap * (nl - 1)) / nl, off = (B - nw * od - (nw - 1) * gap) / 2;
    for (let i = 0; i < nl; i++) for (let j = 0; j < nw; j++)
      s += svgEl("rect", { x: X(z0 + i * (tl + gap)), y: Y(off + j * (od + gap)), width: tl * sx, height: od * sx, rx: od * sx / 2, fill: gold, opacity: 0.35, stroke: gold });
  } else {
    const wt = g.hold_top_width_m || B - 2;
    s += svgEl("rect", { x: X(z0), y: Y((B - wt) / 2), width: (z1 - z0) * sx, height: wt * sx, fill: gold, opacity: 0.25, stroke: gold });
  }
  s += svgEl("text", { x: X(L) + 4, y: Y(B / 2) + 4, "font-size": 11, fill: css("--muted") }, `B ${fmt(B, 1)}`);

  // MIDSHIP SECTION (own scale)
  const sy0 = Y(B) + 40, ss = Math.min(220 / B, 150 / (D + above + 0.5));
  const cx = pad + 20, SX = (m) => cx + m * ss, SY = (m) => sy0 + (D + above) * ss - m * ss;
  s += svgEl("text", { x: pad, y: sy0 - 8, "font-size": 12, fill: gold, "font-weight": 700, "letter-spacing": "1" }, "MIDSHIP SECTION");
  s += svgEl("rect", { x: SX(0), y: SY(D), width: B * ss, height: D * ss, fill: "#fff" });
  if (gas && g.tank_outer_diameter_m) {
    const nw = g.n_tanks_wide || 1, od = g.tank_outer_diameter_m, gap = 0.6, off = (B - nw * od - (nw - 1) * gap) / 2, zb = g.bottom_clearance_m || 0.5;
    for (let j = 0; j < nw; j++)
      s += svgEl("circle", { cx: SX(off + od / 2 + j * (od + gap)), cy: SY(zb + od / 2), r: od / 2 * ss, fill: gold, opacity: 0.35, stroke: gold });
  } else {
    const hh = g.hold_height_m || D, wt = g.hold_top_width_m || B - 2, wb = g.hold_bottom_width_m || wt, db = D + 1 - hh;
    s += svgEl("line", { x1: SX(0), x2: SX(B), y1: SY(db), y2: SY(db), stroke: steel });
    s += svgEl("polygon", { points: `${SX((B - wt) / 2)},${SY(D + 1)} ${SX((B + wt) / 2)},${SY(D + 1)} ${SX((B + wb) / 2)},${SY(db)} ${SX((B - wb) / 2)},${SY(db)}`,
      fill: gold, opacity: 0.25, stroke: gold });
  }
  s += svgEl("rect", { x: SX(-0.5), y: SY(x.draught_m), width: (B + 1) * ss, height: x.draught_m * ss, fill: water, opacity: 0.55 });
  s += svgEl("rect", { x: SX(0), y: SY(D), width: B * ss, height: D * ss, fill: "none", stroke: navy, "stroke-width": 2 });
  const tx = SX(B) + 24, lines = [
    `Beam ${fmt(B, 2)} m · Depth ${fmt(D, 2)} m`, `Draught ${fmt(x.draught_m, 2)} m (max ${fmt(x.draught_max_m, 2)} m)`,
    `Light draught ${fmt(x.light_draught_m, 2)} m`,
    gas ? `${r.arrangement.n_wide} across × ${r.arrangement.n_long} in line = ${g.n_tanks_total} Type C tanks, ${fmt(g.tank_outer_diameter_m, 2)} m OD`
        : `Hold ${fmt(g.hold_top_width_m, 1)} m wide × ${fmt(g.hold_height_m, 1)} m high`,
    `Cargo zone ${fmt(g.cargo_zone_length_m, 1)} m of ${fmt(L, 1)} m`];
  if (gas) lines.push(`${fmt(r.arrangement.per_tank_m3)} m³ per tank · side clearance ${fmt(r.arrangement.side_clearance_m, 2)} m`,
    `${{ IGC_2G_EXACT: "IGC 2G exact", ADN_G: "ADN type G", IGC_2G: "IGC 2G stepped" }[r.arrangement.ruleset]}, fill ${fmt(r.arrangement.fill_ratio * 100)} % · best of ${r.arrangement.candidates_tried} arrangements`);
  lines.forEach((t, i) => (s += svgEl("text", { x: tx, y: sy0 + 18 + i * 20, "font-size": 13, fill: css("--ink") }, t)));
  const H = Math.max(sy0 + (D + above) * ss + 20, sy0 + 18 + lines.length * 20);
  $("#drawcap").textContent = "Profile, plan and midship section, to scale within each view. " +
    (r.self_propelled ? "Self-propelled: the stern block holds machinery and accommodation." : "Pushed barge — the pusher is a separate vessel.");
  $("#drawing").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Concept arrangement">${s}</svg>`;
}

/* ---------- Speed–power chart ---------- */
function renderChart(r) {
  const W = 900, H = 320, m = { l: 60, r: 20, t: 16, b: 44 };
  const curves = r.curves.filter((c) => c.points.length);
  if (!curves.length) { $("#chart").innerHTML = ""; return; }
  const xs = curves.flatMap((c) => c.points.map((p) => p.kn)), ys = curves.flatMap((c) => c.points.map((p) => p.kw));
  const xmax = Math.max(...xs), ymax = Math.max(...ys) * 1.1 || 1;
  const X = (v) => m.l + (v / xmax) * (W - m.l - m.r), Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const colors = [css("--navy"), css("--gold")];
  let s = "";
  for (let i = 0; i <= 5; i++) {
    const v = (ymax / 5) * i;
    s += svgEl("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: "#EEE8DC" });
    s += svgEl("text", { x: m.l - 6, y: Y(v) + 4, "font-size": 11, "text-anchor": "end", fill: css("--muted") }, fmt(v));
  }
  for (let k = 0; k <= Math.floor(xmax); k += 1)
    s += svgEl("text", { x: X(k), y: H - m.b + 16, "font-size": 11, "text-anchor": "middle", fill: css("--muted") }, k);
  s += svgEl("text", { x: (W + m.l) / 2, y: H - 6, "font-size": 12, "text-anchor": "middle", fill: css("--ink") }, "Speed through water (knots)");
  s += svgEl("text", { x: 14, y: H / 2, "font-size": 12, "text-anchor": "middle", fill: css("--ink"), transform: `rotate(-90 14 ${H / 2})` }, "Delivered power (kW)");
  curves.forEach((c, i) => {
    const pts = c.points.map((p) => `${X(p.kn)},${Y(p.kw)}`).join(" ");
    s += svgEl("polyline", { points: pts, fill: "none", stroke: colors[i % 2], "stroke-width": 2.5 });
    const last = c.points[c.points.length - 1];
    s += svgEl("text", { x: X(last.kn) - 4, y: Y(last.kw) - 8, "font-size": 12, fill: colors[i % 2], "text-anchor": "end", "font-weight": 700 }, c.name);
    if (c.limiting_speed_kn) {
      s += svgEl("line", { x1: X(c.limiting_speed_kn), x2: X(c.limiting_speed_kn), y1: m.t, y2: H - m.b, stroke: css("--red"), "stroke-dasharray": "4 4" });
      s += svgEl("text", { x: X(c.limiting_speed_kn) - 4, y: H - m.b - 8, "font-size": 11, fill: css("--red"), "text-anchor": "end" }, `channel limiting speed ${fmt(c.limiting_speed_kn, 1)} kn`);
    }
  });
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Speed against delivered power">${s}</svg>`;
  const ch = curves.find((c) => c.name === "Channel");
  $("#chartcap").textContent = "Delivered power for this hull alone; the pusher's own hull resistance and propulsor efficiency are not included." +
    (ch ? ` Channel blockage (midship area ÷ channel area): ${fmt(ch.blockage * 100, 1)} %.` : "");
}

/* ---------- Intact stability (gas) ---------- */
function renderStability(r) {
  const st = r.stability, card = $("#stabcard");
  card.hidden = !st;
  if (!st) return;
  const v = $("#stabverdict");
  v.className = "governs" + (st.ok ? "" : " fail");
  v.textContent = st.ok ? `Meets ${st.criteria_set} in all three loading conditions.`
    : `Fails ${st.criteria_set}. Governing condition: ${st.governing.toLowerCase()}.`;

  const W = 900, H = 300, m = { l: 56, r: 20, t: 14, b: 42 };
  const conds = st.conditions.filter((c) => c.gz.length);
  const all = conds.flatMap((c) => c.gz.map((p) => p[1]));
  const ymax = Math.max(0.2, ...all) * 1.1, ymin = Math.min(0, ...all) * 1.1;
  const X = (d) => m.l + (d / 60) * (W - m.l - m.r), Y = (g) => m.t + (ymax - g) / (ymax - ymin) * (H - m.t - m.b);
  const colors = [css("--navy"), css("--gold"), "#3A7CA5"];
  let s = "";
  for (let i = 0; i <= 4; i++) {
    const g = ymin + (ymax - ymin) * i / 4;
    s += svgEl("line", { x1: m.l, x2: W - m.r, y1: Y(g), y2: Y(g), stroke: "#EEE8DC" });
    s += svgEl("text", { x: m.l - 6, y: Y(g) + 4, "font-size": 11, "text-anchor": "end", fill: css("--muted") }, fmt(g, 2));
  }
  s += svgEl("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: css("--muted") });
  for (let d = 0; d <= 60; d += 10)
    s += svgEl("text", { x: X(d), y: H - m.b + 16, "font-size": 11, "text-anchor": "middle", fill: css("--muted") }, `${d}°`);
  s += svgEl("text", { x: (W + m.l) / 2, y: H - 6, "font-size": 12, "text-anchor": "middle", fill: css("--ink") }, "Heel angle");
  s += svgEl("text", { x: 14, y: H / 2, "font-size": 12, "text-anchor": "middle", fill: css("--ink"), transform: `rotate(-90 14 ${H / 2})` }, "GZ, fluid (m)");
  conds.forEach((c, i) => {
    s += svgEl("polyline", { points: c.gz.map(([d, g]) => `${X(d)},${Y(g)}`).join(" "), fill: "none", stroke: colors[i], "stroke-width": 2.5 });
    const [dm, gm] = c.gz.reduce((a, b) => (b[1] > a[1] ? b : a));
    s += svgEl("text", { x: X(dm), y: Y(gm) - 8, "font-size": 12, fill: colors[i], "text-anchor": "middle", "font-weight": 700 }, c.name);
    if (c.deck_edge_deg && c.deck_edge_deg < 60)
      s += svgEl("circle", { cx: X(c.deck_edge_deg), cy: Y(c.gz[Math.round(c.deck_edge_deg)][1]), r: 4, fill: "#fff", stroke: colors[i], "stroke-width": 2 });
  });
  $("#gzchart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Righting lever curves">${s}</svg>` +
    `<p class="caption">Righting lever after free-surface correction. Circles mark deck-edge immersion.</p>`;

  $("#stabtable").innerHTML = `<tr><th>Condition</th><th class="num">Cargo (t)</th><th class="num">Tank fill</th><th class="num">Δ (t)</th>` +
    `<th class="num">T (m)</th><th class="num">KG (m)</th><th class="num">GM solid</th><th class="num">Free surface</th>` +
    `<th class="num">GM fluid</th><th class="num">Max GZ</th><th>Verdict</th></tr>` +
    st.conditions.map((c) => `<tr><td>${c.name}</td><td class="num">${fmt(c.cargo_t)}</td><td class="num">${fmt(c.fill * 100)} %</td>` +
      `<td class="num">${fmt(c.displacement_t)}</td><td class="num">${fmt(c.draught_m, 2)}</td><td class="num">${fmt(c.kg_m, 2)}</td>` +
      `<td class="num">${fmt(c.gm_solid_m, 2)}</td><td class="num">${fmt(c.free_surface_m, 2)}</td><td class="num">${fmt(c.gm_fluid_m, 2)}</td>` +
      `<td class="num">${fmt(c.max_gz_m, 2)} m at ${fmt(c.max_gz_deg)}°</td>` +
      `<td class="${c.criteria.every((x) => x.ok) ? "ok" : "bad"}">${c.criteria.every((x) => x.ok) ? "Pass" : "Fail"}</td></tr>`).join("");

  const gov = st.conditions.find((c) => c.name === st.governing);
  $("#crittable").innerHTML = `<tr><th>Criterion</th><th class="num">Value</th><th class="num">Required</th><th></th><th>Source</th></tr>` +
    gov.criteria.map((x) => `<tr><td>${x.name}</td><td class="num">${fmt(x.value, 3)}</td><td class="num">≥ ${x.limit}</td>` +
      `<td class="${x.ok ? "ok" : "bad"}">${x.ok ? "✓" : "✕"}</td><td>${x.source}</td></tr>`).join("");
  $("#stablims").innerHTML = st.limitations.map((l) => `<li>${l}</li>`).join("");
}

function renderChecks(r) {
  $("#checks").innerHTML = r.checks.map((c) =>
    `<li class="${c.ok ? "ok" : "fail"}">${c.name[0].toUpperCase() + c.name.slice(1)} <span class="m">— ${c.message}</span></li>`).join("");
  $("#warnings").innerHTML = r.warnings.map((w) => `<li>${w}</li>`).join("");
}

/* ---------- Matching standard classes ---------- */
function dist(v, rng) {
  if (!rng) return 1;
  const [a, b] = rng; return v < a ? (a - v) / v : v > b ? (v - b) / v : 0;
}
function renderMatches(p) {
  const mode = p.vessel === "gas_barge" ? "liquid" : "dry_bulk";
  const ranked = CLASSES.filter((c) => c.loa_m && c.beam_m).map((c) => ({
    c, d: dist(p.loa_m, c.loa_m) + dist(p.beam_m, c.beam_m) + (c.cargo_modes.some((m) => m.startsWith(mode.slice(0, 3))) ? 0 : 0.15)
      + (c.formation === "pushed_barge" ? 0 : 0.05),
  })).sort((a, b) => a.d - b.d).slice(0, 8);
  const rng = (r, d = 1) => !r ? "–" : r[0] === r[1] ? fmt(r[0], d) : `${fmt(r[0], d)}–${fmt(r[1], d)}`;
  $("#matches").innerHTML = `<tr><th>Class</th><th>Family</th><th>Type</th><th class="num">LOA (m)</th><th class="num">Beam (m)</th>` +
    `<th class="num">Draught (m)</th><th class="num">DWT (t)</th><th class="num">Real vessels</th></tr>` +
    ranked.map(({ c }) => `<tr class="click" data-id="${c.id}" title="Use this class's length and beam">` +
      `<td>${c.id}</td><td>${c.family}</td><td>${c.formation.replace("_", " ")}</td><td class="num">${rng(c.loa_m)}</td>` +
      `<td class="num">${rng(c.beam_m)}</td><td class="num">${rng(c.draught_m, 2)}</td><td class="num">${rng(c.dwt_t, 0)}</td>` +
      `<td class="num">${c.reference_vessels.length || "–"}</td></tr>`).join("");
  document.querySelectorAll("#matches tr.click").forEach((tr) =>
    tr.addEventListener("click", () => { applyClass(tr.dataset.id); update(); }));
}

boot();
