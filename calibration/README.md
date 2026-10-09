# Calibration

`cases.yaml` holds real vessels (and published design points) with their sources.
`python -m vessel_designer.calibration` runs them through the core and writes `results.md`.
The pass **measures**; it does not tune. Each correction is a separate change with its evidence.

## Pass 1 findings (2026-10-06, core as ported from Ankobra @ 4c29cab1)

1. **Barge lightship is overestimated by 31–111 %.** The bulk branch adds Ankobra's sloped-hopper
   structure (14 mm inner bottom and hopper plates, × structure factor 1.4) on top of 0.10 t/m³ × L·B·D.
   Real US, Paraná and Danube barges are box holds and much lighter. Observed LS/(L·B·D):
   Pará Mississippi 0.095, Danube 0.122, Victor container barge 0.171 (shallow 2.8 m depth with a
   20 mm sheer strake, so a high ratio). Padovezi's 0.12 is closest on average (−30 % to +26 %).
   The CN draft formula overestimates barges (+28 % to +76 %); it was fitted to motor vessels.
2. **Default Cb = 0.85 is too low for barges.** Implied Cb is 0.90–1.0 on LOA; DWT comes out
   19–33 % low. Two cases imply Cb > 1 (Pará 1.035, LHG 1.013), which is impossible on LOA —
   so their DWT, lightship or units do not belong to the same condition. Flagged, not used to fit.
3. **The Yangtze design points are themselves model output.** Every row implies exactly
   Cb = 0.835 on LOA, so the draft note computed displacement from a fixed Cb. They are a check on
   *our* model against *theirs*, not against built ships.
4. **Installed power is 1.7–2.1 × our deep-water delivered power.** A normal margin
   (85 % MCR, 15 % sea margin) gives about 1.4 ×. The remaining gap is either shallow-water
   resistance on the Yangtze (h/T not stated in the note) or the core under-predicting resistance
   for full inland hulls. Needs a built vessel with a trial speed–power point to separate the two.

## Corrections applied (2026-10-06)

- **Barge lightship by hold type.** `BargeCapacityInputs.hold_type` = `box` | `container` uses
  k × L·B·D; `sloped_hopper` (the default) keeps the Ankobra build-up unchanged. k is fitted by the
  harness into `factors.yaml` — box 0.109 t/m³ (n = 3, range 0.095–0.122), container 0.171 (n = 1,
  **one point: in-sample, not validated**).
- **Box-barge Cb = 0.928 on LOA** (n = 7, range 0.883–0.995), fitted the same way. Two cases
  excluded with reasons recorded.
- Result on the cases: box-barge lightship within −11 % to +15 %; deadweight within −8 % to +6 %
  on the fitted cases. These are **in-sample** errors. The next real lightship is the first
  out-of-sample test.
- Kirby's barge database (draft/tonnage tables from 0 t) is unreachable from this machine
  (host times out; kirbycorp.com itself answers). Still the best source of more lightships.

## Proposed corrections — original list

- Barge lightship: replace the hopper-structure term for box barges with a calibrated
  k × L·B·D, k fitted per hold type (box hopper ≈ 0.095–0.12; container ≈ 0.17), and keep the
  structural build-up only for real sloped-hopper holds. Needs ≥ 3 more observed lightships.
- Cb: make it a required Brief input; default per Hull family from the implied values
  (box barge ≈ 0.93–0.97).
- Power: hold until a built-vessel speed–power point exists; report the margin explicitly.
