"""Worked example: size a liquefied-propane barge on a standard Chinese Class II hull.

    python examples/quickstart.py
"""
from vessel_designer.core.barge_capacity import BargeCapacityInputs, compute
from vessel_designer.core.gas_arrangement import fit
from vessel_designer.core.vessel_standards import get_standard

# 1. Start from a standard class, not a bespoke hull.
cls = get_standard("CN_II_motor")
loa, beam = cls.loa_m[1], cls.beam_m
print(f"Class {cls.family} {cls.class_name}: {loa:.0f} m x {beam:.1f} m, "
      f"{cls.dwt_nominal_t:,.0f} t class deadweight")

# 2. One capacity run: the core picks a tank arrangement for this hull.
auto = compute(BargeCapacityInputs(loa=loa, beam=beam, depth=6.5, cargo_type="LPG_propane"))
print(f"Single run : {auto.n_tanks_wide} tanks abreast, OD {auto.tank_outer_diameter_m:.2f} m, "
      f"{auto.cargo_capacity_t:,.0f} t, laden draught {auto.full_load_draft_m:.2f} m")

# 3. Search the tank arrangement for the most cargo per journey at a 4.4 m draught cap.
#    The single run can settle on the worse of two self-consistent arrangements; the search
#    tries each tanks-abreast count on its own.
best = fit(loa, beam, "LPG_propane", 4.4, ruleset="IGC_2G", depths=(6.5,))
print(f"Searched   : {best.n_tanks_wide} tank(s) abreast, OD {best.tank_od_m:.2f} m, "
      f"{best.payload_t:,.0f} t ({best.binding}-bound), draught {best.draft_at_payload_m:.2f} m")
if not best.feasible:
    print("  INFEASIBLE: no arrangement passes its checks")
for msg in best.failed_checks:
    print("  check failed:", msg)
