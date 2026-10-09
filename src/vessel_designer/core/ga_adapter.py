"""Drive the GA drawings from ``barge_capacity`` — the current model — not the legacy one.

WHY THIS EXISTS. A GA drawer (e.g. an SVG GA module) reads ``models.BargeInputs`` /
``BargeResults``, which is the LEGACY ATB barge model: it sizes its own hull and tanks. ``barge_capacity`` is the
standardised module the rest of the project uses, and the two DISAGREE — on a CN II motor
vessel the legacy solver returns a 9.95 m moulded depth, 5.01 m draft and 12.80 m tank OD
where ``barge_capacity`` gives 5.4 m, 4.40 m and 11.25 m.

Drawing the legacy numbers on a pack whose tonnages come from ``barge_capacity`` would be the
exhibit-vs-model drift that is easy to miss and costly to find late. So this adapter builds the
drawing's own structures FROM the capacity result: the picture is then a view of the current
model rather than a second model that happens to look similar.

It converts geometry ONLY. Nothing here recomputes a capacity, a weight or a draft — every
number it passes through was produced by ``barge_capacity`` or ``journey_derating``.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Optional

from .models import BargeInputs, BargeResults, TankResult
from .barge_capacity import BargeCapacityInputs, BargeCapacityResult


def is_gas(res: BargeCapacityResult) -> bool:
    return res.phase == "liquid_gas"


def _tank_result(inp: BargeCapacityInputs, res: BargeCapacityResult) -> TankResult:
    """A TankResult carrying barge_capacity's tank geometry, for the drawing to read."""
    od = res.tank_outer_diameter_m
    if od is None:
        raise ValueError("no tank geometry: this is a dry-bulk result, use a hopper view "
                         "rather than the tank GA")
    # The cargo space is what is left after INSULATION and then the steel shell come off
    # the outer diameter -- the same build-up `tanks.calculate_tank_arrangement` uses.
    # Taking only the steel off would draw the bore 0.70 m too wide on a 350 mm insulation
    # and make the cylinder length that reconciles the volume come out short. Read the inner diameter the capacity model already reported; fall back to
    # the build-up only if it is absent.
    wall = (inp.tank_wall_thickness or 25.0) / 1000.0
    insul = (res.insulation_thickness_mm if res.insulation_thickness_mm is not None
             else 350.0) / 1000.0
    idia = res.tank_inner_diameter_m
    if idia is None:
        idia = od - 2 * insul - 2 * wall
    idia = max(0.1, idia)
    # cylindrical length is DETERMINED by the volume the capacity model computed
    v_tank = res.cargo_volume_m3 / inp.fill_ratio / max(res.n_tanks_total, 1)
    cyl = v_tank / (math.pi * (idia / 2) ** 2)
    head = idia / 2.0                                   # hemispherical heads
    return TankResult(
        n_tanks_wide=res.n_tanks_wide, n_tanks_long=inp.n_tanks_long,
        n_tanks_total=res.n_tanks_total,
        outer_diameter=od, inner_diameter=idia,
        overall_tank_length=cyl + 2 * head, cylinder_length=cyl, head_length=head,
        volume_per_tank=v_tank, volume_cylinder=math.pi * (idia / 2) ** 2 * cyl,
        volume_heads=(4 / 3) * math.pi * (idia / 2) ** 3,
        total_tank_volume=v_tank * res.n_tanks_total,
        cargo_volume=res.cargo_volume_m3,
        tank_shell_weight=float("nan"),                 # not drawn; never invent one
        insulation_weight=float("nan"),
        tank_top_above_keel=res.bottom_clearance_m + od,
        cylinder_wall_thickness=inp.tank_wall_thickness or 25.0,
    )


def to_ga(inp: BargeCapacityInputs, res: BargeCapacityResult,
          laden_draft_m: Optional[float] = None, motor_vessel: bool = True):
    """(BargeInputs, BargeResults) for ``svg_drawings``, built from a capacity result.

    ``laden_draft_m`` overrides the full-load draft with the channel-limited one from
    ``journey_derating`` — that is the draft the vessel actually floats at on this river, and
    it is the one a reader of the pack needs to see.

    ``motor_vessel=True`` sets ``tug_length=0``, which ``svg_drawings`` reads as
    self-propelled: aft machinery and accommodation inside the hull, no pushed tug.
    """
    draft = float(laden_draft_m if laden_draft_m is not None else res.full_load_draft_m)
    gi = BargeInputs(
        loa=inp.loa, beam=inp.beam, depth=inp.depth, max_draft=draft,
        # 0 = no bridge clearance passed. The old 20.0 was a placeholder that
        # drew a limit line nothing was gated on.
        vertical_clearance=0.0, vessel_type=inp.vessel_type,
        cargo_type=inp.cargo_type, fill_ratio=inp.fill_ratio,
        # DERIVED voids from the capacity result -- never the old LOA fractions, which
        # knew nothing about the thrusters, the containers or the gas-code separation.
        bow_non_tank_length=res.bow_void_length_m,
        stern_non_tank_length=res.stern_void_length_m,
        bow_rake_length=res.bow_rake_length_m or 0.0,
        aft_arrangement=res.aft_arrangement, separation=res.separation,
        n_tanks_wide=res.n_tanks_wide, n_tanks_long=inp.n_tanks_long,
        tank_wall_thickness=inp.tank_wall_thickness or 25.0,
        insulation_thickness=(res.insulation_thickness_mm
                              if res.insulation_thickness_mm is not None else 350.0),
        dome_height=inp.dome_height, tank_support_height=inp.tank_support_height,
        side_clearance=res.side_clearance_m,
        double_bottom_height=res.bottom_clearance_m or inp.double_bottom_height_bulk,
        block_coefficient=inp.block_coefficient, water_density=inp.water_density,
        tug_length=0.0 if motor_vessel else 25.0,
    )
    gr = BargeResults(
        inputs=gi, tanks=(_tank_result(inp, res) if is_gas(res) else None),
        cargo_type=res.cargo_type, cargo_density=res.cargo_density_t_per_m3 * 1000.0,
        cargo_mass=res.cargo_capacity_t, weights=None,
        displacement=res.displacement_t, deadweight=res.deadweight_t,
        draft=draft, freeboard=inp.depth - draft, min_freeboard_ok=True,
        air_draft=res.air_draft_m, air_draft_ok=True, stability=None, stability_ok=True,
        trim=0.0, total_depth_required=inp.depth,
        air_draft_unladen=res.air_draft_light_m or 0.0,
        light_draft=res.light_draft_m or 0.0,
        air_draft_navigating_unladen=res.air_draft_navigating_light_m or 0.0,
        protective_location=None,
        binding_constraints=[], warnings=list(res.warnings),
    )
    return gi, gr
