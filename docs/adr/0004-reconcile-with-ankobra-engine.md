# Reconcile with the Ankobra engine; this repo is the single master of the vessel code

The vessel core was ported from the Ankobra engine (`engine/vessel_design/`) on 2026-10-06 (ADR 0002).
Both copies then lived on. This repo is now the **single master**: the Ankobra copy will be retired
and Ankobra, and the channel-design package to be extracted from it, will import from here.

Reconciled 2026-10-09 against Ankobra `origin/main` at `5d57e611`. No commit on Ankobra `origin/main`
(or any other Ankobra branch) touches the reconciled modules after the port, so nothing flows from
Ankobra to here except the two modules that were left behind.

## Drifted modules

| Module | Difference | Decision |
|---|---|---|
| `hull` | none | keep |
| `hydrostatics` | none | keep |
| `journey_derating` | none | keep |
| `models`, `checks`, `tanks`, `weights` | none | keep |
| `barge_capacity` | here only: `hold_type` + `lightship_k_t_per_m3` (calibration pass 1, box/container holds); `IGC_2G_EXACT` clearance loop (`d_vc_exact`); `gas_basis` on the result (feeds `gas_stability`) | keep — intentional improvements. All new fields default to the old behaviour, so Ankobra callers get the same numbers. |
| `protective_location` | here only: `ADN_G` and `IGC_2G_EXACT` rulesets, `d_vc_exact`; `required_bottom_protection` folded into the clearance functions | keep — the "IGC_2G" reading is unchanged. No caller outside the module used `required_bottom_protection`. |

## Modules the channel code needs

The channel code imports `channel_design`, `channel_rules`, `barge_capacity`, `vessel_standards`,
`journey_derating`, `ga_adapter`, `spine.geo_loader` and `electric_excavation` from `vessel_design`.

| Module | Vessel code? | Decision |
|---|---|---|
| `barge_capacity` | yes | already here; API is a superset of Ankobra's |
| `journey_derating` | yes | already here; identical |
| `checks` (`Check`, `all_ok`) | yes, shared | already here; identical. The channel package may import it from here. |
| `vessel_standards` | yes | **ported** with its 11 tests. Same names (`VESSEL_STANDARDS`, `VesselStandard`, `get_standard`, `standards_for`, `validate_catalogue`) and the same data. Comments and `notes` strings reworded to drop project history. |
| `ga_adapter` | yes | **ported** (`to_ga`, `is_gas`), new tests (4). Depends only on `models` and `barge_capacity`. |
| `channel_design`, `channel_rules`, `channel_width_prdw`, `channel/` | no | leave — channel package (stage 3) |
| `spine.geo_loader` | no — channel-geometry artifact loading (volumes, weirs, reach) | leave — channel package |
| `electric_excavation` | no — cost code | leave — stays in Ankobra |

## Consequences

- `vessel_standards` overlaps `catalogue/` (183 classes). It stays as the small typed lookup the
  channel code needs; deriving it from the catalogue is a later step.
- `CN_II_motor.moulded_depth_m = 6.5` is a project design value, not a published class value. It is
  kept so Ankobra's numbers do not move when it switches to this package. Moving it into the consumer
  is a candidate for the stage-4 rewire.
- `ga_adapter` builds the structures a GA drawer reads. This repo has no SVG GA drawer (ADR 0003); the
  adapter is here so callers keep one import path.
