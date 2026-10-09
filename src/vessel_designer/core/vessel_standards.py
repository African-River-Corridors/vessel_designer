"""Standard inland-vessel classes — a compact catalogue with a stable lookup API.

WHY THIS EXISTS. A fleet built to a STANDARD class, not a bespoke hull, lets a vessel built
or chartered elsewhere come onto a waterway without a custom build. This module holds those
classes as reference data plus a validity check, not an Inputs/Result/compute triple. The
fuller class list lives in ``catalogue/``; this module is the small, typed subset that
channel-design code looks up by id (``get_standard``).

TWO CLASSIFICATION FAMILIES, and they encode different philosophies:

  * CEMT/ITF-1992 (PIANC WG 141 Table 2.1, p15) and the Dutch 2011 update (Table 2.2,
    p16). European waterways are canalised and deep, so tonnage is bought with DRAUGHT
    on a narrow hull. CEMT'92 caps a single hull at 11.4 m beam; wider tonnage is a
    2-abreast pushed convoy at 22.8 m.
  * Chinese (WG 141 Table 2.3, p16; Chinese channel rules Appendix A.3, p162-164). Chinese
    inland waterways are shallow rivers, so tonnage is bought with BEAM: single motor
    vessels reach 14.8 m (2,000 t) and 16.2 m (3,000 t) at 2.6-3.2 m draught. Class
    numbering runs BACKWARDS from Europe's — Class I is the largest.

The Dutch 2011 update moved Europe the same way (VIa motor vessels at 13.5-17.0 m beam),
so CEMT'92 read alone will mislead. PIANC convened WG 179 to revise it.

WHY THE CHOICE IS LOAD-BEARING. Design channel depth follows draught, and design bend
radius follows LENGTH (R_min = k x LOA). Pairing barges IN LINE doubles LOA, so R_min
roughly doubles too — usually far more expensive on a meandering river than pairing ABREAST.

Dimensions are the CLASS definition, not a specific hull. Draught ranges are the class
range; a project's design draught is its own decision, and the channel depth follows from
it by the channel rules, not from this table.

Pure Python, Pyodide-safe. No I/O.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .checks import Check


@dataclass(frozen=True)
class VesselStandard:
    """One standard inland-vessel or convoy class."""

    standard_id: str
    family: str                  # "CEMT" | "CEMT-NL-2011" | "CN"
    class_name: str              # the class label in its own family, e.g. "VIa", "II"
    formation: str               # "motor_vessel" | "pushed_convoy" | "coupled_unit"
    loa_m: Tuple[float, float]   # (min, max) overall length of the vessel/convoy
    beam_m: float                # overall beam of the vessel/convoy
    draught_m: Tuple[float, float]   # (min, max) design draught range for the class
    dwt_t: Tuple[float, float]   # (min, max) deadweight
    n_abreast: int = 1           # barges side by side (sets beam)
    n_in_line: int = 1           # barges end to end (sets LOA, and so R_min)
    unit_beam_m: Optional[float] = None   # beam of ONE barge, where the class is a convoy
    min_bridge_clearance_m: Optional[float] = None   # class requirement, NOT our bridges
    #: Moulded depth, where the class has been sized as a modified class rather than taken
    #: as published. None means "not specified" and the caller must say what it assumes
    #: (draught + 1.0 m is a common rule of thumb, never a class property). A number here
    #: is a DESIGN DECISION, not a published value.
    moulded_depth_m: Optional[float] = None
    source: str = ""
    cargo_modes: Tuple[str, ...] = ("dry_bulk", "liquid_gas")
    notes: str = ""

    @property
    def loa_nominal_m(self) -> float:
        return 0.5 * (self.loa_m[0] + self.loa_m[1])

    @property
    def draught_nominal_m(self) -> float:
        return 0.5 * (self.draught_m[0] + self.draught_m[1])

    @property
    def dwt_nominal_t(self) -> float:
        return 0.5 * (self.dwt_t[0] + self.dwt_t[1])

    def r_min_m(self, radius_multiple: float = 3.0) -> float:
        """Design minimum bend radius at the LONG end of the class length range.

        Sizing on the short end would under-call the radius for the same class.
        """
        return radius_multiple * self.loa_m[1]


# --- the catalogue -------------------------------------------------------------------
# CEMT/ITF-1992: WG 141 Table 2.1 (p15). Bridge clearances are the CLASS requirement and
# are driven by container stacking; a low-profile pushed dry-bulk barge needs far less.
# Check them against the real bridges on the route: they are class requirements, not a spec.
VESSEL_STANDARDS: Dict[str, VesselStandard] = {
    "CEMT_IV": VesselStandard(
        standard_id="CEMT_IV", family="CEMT", class_name="IV", formation="motor_vessel",
        loa_m=(80.0, 85.0), beam_m=9.5, draught_m=(2.5, 2.5), dwt_t=(1000.0, 1500.0),
        min_bridge_clearance_m=5.25, source="WG 141 Table 2.1 (p15)",
    ),
    "CEMT_Va": VesselStandard(
        standard_id="CEMT_Va", family="CEMT", class_name="Va", formation="motor_vessel",
        loa_m=(95.0, 110.0), beam_m=11.4, draught_m=(2.5, 4.5), dwt_t=(1500.0, 3000.0),
        min_bridge_clearance_m=5.25, source="WG 141 Table 2.1 (p15)",
        notes="The workhorse European barge. The unit that pairs abreast into VIa.",
    ),
    "CEMT_Vb": VesselStandard(
        standard_id="CEMT_Vb", family="CEMT", class_name="Vb", formation="pushed_convoy",
        loa_m=(172.0, 185.0), beam_m=11.4, draught_m=(2.5, 4.5), dwt_t=(3200.0, 6000.0),
        n_in_line=2, unit_beam_m=11.4, min_bridge_clearance_m=7.0,
        source="WG 141 Table 2.1 (p15)",
        notes="2 IN LINE. R_min ~555 m at 3xLOA — a tight meander cannot usually deliver it.",
    ),
    "CEMT_VIa": VesselStandard(
        standard_id="CEMT_VIa", family="CEMT", class_name="VIa", formation="pushed_convoy",
        loa_m=(95.0, 110.0), beam_m=22.8, draught_m=(2.5, 4.5), dwt_t=(3200.0, 6000.0),
        n_abreast=2, unit_beam_m=11.4, min_bridge_clearance_m=7.0,
        source="WG 141 Table 2.1 (p15); c_C row in Table E.5 (p261)",
        notes="2 Va ABREAST. Short and wide, so WG 141 p101 "
              "names this class as the worst case for bend widening (c_C 0.6 loaded "
              "downstream, 1.6 empty downstream).",
    ),
    "CEMT_VIa_motor_NL2011": VesselStandard(
        standard_id="CEMT_VIa_motor_NL2011", family="CEMT-NL-2011", class_name="VIa",
        formation="motor_vessel",
        loa_m=(110.0, 135.0), beam_m=17.0, draught_m=(4.0, 4.0), dwt_t=(6000.0, 6000.0),
        min_bridge_clearance_m=7.0,
        source="WG 141 Table 2.2 (p16) + Table 2.5 (p17)",
        notes="Post-CEMT'92 wide single hull. Shows Europe moving toward the Chinese "
              "beam-over-draught trade. 2,400 kW, 1,135 kW bow thruster (Table 2.5).",
    ),
    # Chinese: WG 141 Table 2.3 (p16). Class numbering runs backwards — I is largest.
    "CN_I_motor": VesselStandard(
        standard_id="CN_I_motor", family="CN", class_name="I", formation="motor_vessel",
        loa_m=(95.0, 95.0), beam_m=16.2, draught_m=(3.2, 3.2), dwt_t=(3000.0, 3000.0),
        source="WG 141 Table 2.3 (p16); channel rules Table A.2 (p163)",
        notes="SINGLE HULL at 3,000 t with no pairing: R_min only ~285 m at 3xLOA.",
    ),
    "CN_II_motor": VesselStandard(
        standard_id="CN_II_motor", family="CN", class_name="II", formation="motor_vessel",
        loa_m=(90.0, 90.0), beam_m=14.8, draught_m=(2.6, 2.6), dwt_t=(2000.0, 2000.0),
        source="WG 141 Table 2.3 (p16)",
        moulded_depth_m=6.5,
        notes="2,000 t on 2.6 m draught in a single standard hull. MODIFIED CLASS: "
              "moulded depth 6.5 m, not the draught+1.0 m rule of thumb. 6.5 m is where "
              "dry bulk stops being volume-bound and exactly consumes 4.40 m of available "
              "draught. Beyond it payload FALLS — the steel outweighs the cargo.",
    ),
    "CN_III_motor": VesselStandard(
        standard_id="CN_III_motor", family="CN", class_name="III", formation="motor_vessel",
        loa_m=(85.0, 85.0), beam_m=10.8, draught_m=(2.0, 2.0), dwt_t=(1000.0, 1000.0),
        source="WG 141 Table 2.3 (p16); channel rules Table A.2 (p163): width 30 m, R 480 m",
        notes="The SHALLOWEST standard class of real size: 1,000 t on 2.0 m draught. On a "
              "river where depth is the expensive axis this is the one to beat. Its L/B of "
              "7.87 is the top of the Chinese band, so the Chinese width rule applies to it "
              "without extrapolation — unlike every European class.",
    ),
    "CN_III_convoy_2ab": VesselStandard(
        standard_id="CN_III_convoy_2ab", family="CN", class_name="III",
        formation="pushed_convoy",
        loa_m=(167.0, 167.0), beam_m=21.6, draught_m=(2.0, 2.0), dwt_t=(4000.0, 4000.0),
        n_abreast=2, n_in_line=2, unit_beam_m=10.8,
        source="WG 141 Table 2.3 (p16); Table A.2 (p163): width 45 m, R 500 m",
        notes="DWT inferred as 4 x the 1,000 t Class III unit; WG 141 does not tabulate "
              "convoy deadweight. L/B 7.73, inside the Chinese band.",
    ),
    "CN_IV_motor": VesselStandard(
        standard_id="CN_IV_motor", family="CN", class_name="IV", formation="motor_vessel",
        loa_m=(67.5, 67.5), beam_m=10.8, draught_m=(1.6, 1.6), dwt_t=(500.0, 500.0),
        source="WG 141 Table 2.3 (p16); Table A.2 (p163): width 30 m, R 330 m",
        notes="1.6 m draught. Carried as the shallow-draught floor of the comparison.",
    ),
    "CN_II_convoy_2ab": VesselStandard(
        standard_id="CN_II_convoy_2ab", family="CN", class_name="II",
        formation="pushed_convoy",
        # DWT INFERRED, not tabulated: Table 2.3 gives 2,000 t as the CLASS II deadweight
        # for the 90 m motor vessel. The convoy is 2 abreast x 2 in line of 16.2 m barges,
        # so 4 units ~ 8,000 t. WG 141 does not tabulate convoy deadweight; flagged.
        loa_m=(186.0, 186.0), beam_m=32.4, draught_m=(2.6, 2.6), dwt_t=(8000.0, 8000.0),
        n_abreast=2, n_in_line=2, unit_beam_m=16.2,
        source="WG 141 Table 2.3 (p16); Table A.2 (p163): width 70 m, R 560 m",
        notes="4,000 t at only 2.6 m draught, but 186 m long -> R_min ~558 m. A tight meander "
              "cannot usually deliver that radius.",
    ),
    "CN_I_convoy_2ab": VesselStandard(
        standard_id="CN_I_convoy_2ab", family="CN", class_name="I",
        formation="pushed_convoy",
        # DWT INFERRED as above: 4 x the 3,000 t Class I unit. Not tabulated by WG 141.
        loa_m=(223.0, 223.0), beam_m=32.4, draught_m=(3.5, 3.5), dwt_t=(12000.0, 12000.0),
        n_abreast=2, n_in_line=2, unit_beam_m=16.2,
        source="WG 141 Table 2.3 (p16); Table A.2 (p163): width 70 m, R 670 m",
        notes="Chinese Table A.2 prices this at 70 m channel width against PIANC's "
              "91-110 m for the same beam — the clearest single illustration of the "
              "two traditions disagreeing.",
    ),
}


def get_standard(standard_id: str) -> VesselStandard:
    """Look up a standard by id. The single accessor — never hard-code dimensions."""
    try:
        return VESSEL_STANDARDS[standard_id]
    except KeyError:
        raise KeyError(
            f"unknown vessel standard {standard_id!r}; "
            f"known: {', '.join(sorted(VESSEL_STANDARDS))}"
        )


def standards_for(cargo_mode: str) -> List[VesselStandard]:
    """Every standard that can carry this cargo mode ('dry_bulk' or 'liquid_gas')."""
    if cargo_mode not in ("dry_bulk", "liquid_gas"):
        raise ValueError(f"cargo_mode must be dry_bulk or liquid_gas, got {cargo_mode!r}")
    return [s for s in VESSEL_STANDARDS.values() if cargo_mode in s.cargo_modes]


def validate_catalogue(catalogue: Optional[Dict[str, VesselStandard]] = None) -> List[Check]:
    """Assert integrity of the fleet catalogue, as a list of Checks.

    Same contract as machinery.validate_catalogue: reference data earns a validity
    check, not an Inputs/Result/compute triple.
    """
    cat = VESSEL_STANDARDS if catalogue is None else catalogue
    checks: List[Check] = []

    bad = [k for k, v in cat.items() if k != v.standard_id]
    checks.append(Check("unique_ids", not bad,
                        "every key matches its standard_id" if not bad
                        else f"key/standard_id mismatch: {bad}"))

    bad = [k for k, v in cat.items()
           if v.loa_m[0] > v.loa_m[1] or v.draught_m[0] > v.draught_m[1]
           or v.dwt_t[0] > v.dwt_t[1]]
    checks.append(Check("ranges_ordered", not bad,
                        "every (min, max) range is ordered" if not bad
                        else f"inverted range: {bad}"))

    bad = [k for k, v in cat.items() if v.beam_m <= 0 or v.loa_m[0] <= 0]
    checks.append(Check("positive_dimensions", not bad,
                        "all beams and lengths positive" if not bad
                        else f"non-positive dimension: {bad}"))

    # A convoy's overall beam should be its unit beam times the number abreast.
    bad = []
    for k, v in cat.items():
        if v.unit_beam_m and v.n_abreast > 1:
            if abs(v.unit_beam_m * v.n_abreast - v.beam_m) > 0.05:
                bad.append(k)
    checks.append(Check("convoy_beam_consistent", not bad,
                        "convoy beam = unit beam x n_abreast" if not bad
                        else f"beam does not reconcile with n_abreast: {bad}"))

    bad = [k for k, v in cat.items() if not v.source]
    checks.append(Check("source_cited", not bad,
                        "every class cites its table" if not bad
                        else f"no source: {bad}",
                        severity="warning"))

    return checks
