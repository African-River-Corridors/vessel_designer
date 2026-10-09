# Port the vessel core from the Ankobra engine; don't rebuild it

The Ankobra feasibility engine (`engine/vessel_design/`) already holds a tested vessel core: cargo,
Type C tanks and pressure vessels, hull, hydrostatics, weights, capacity, gas separation, protective
location, resistance, squat and electric energy (117 passing tests). We port that core and its tests
into this repo and reshape its interfaces, instead of starting fresh. Ankobra-specific modules (channel,
dredging, locks, haul road, finance) stay behind. Ankobra keeps its own copy until it is separately
migrated to depend on this package.

## Consequences

The ported code carries Ankobra defaults (e.g. Cb 0.85, 28 m tank-length cap, Chinese-yard rates) that
must become inputs. Ported drawings are bespoke SVG; GAs move to `sankofa-draw`.
