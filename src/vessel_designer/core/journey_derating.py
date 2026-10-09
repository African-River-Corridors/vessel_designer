"""Journey / channel de-rating — where volume-bound meets the channel draft cap.

``barge_capacity`` reports VOLUME-BOUND capacity and the full-load draft, deliberately
ignoring the channel. This module applies the downstream weight/draft limit
(``T_max = design_depth - UKC``) and returns the achievable per-journey tonnage plus the
binding limit ("volume" if it floats fully laden, else "draft").

The weight branch inverts the *same* box-hull hydrostatics ``barge_capacity`` uses
(``HullGeometry`` + block coefficient + water density), so the two modules cannot diverge.

Full design basis, worked example, test plan:
    docs/feasibility/proposals/journey-derating.md

Pure Python apart from the hull (numpy) — runs client-side in Pyodide.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .barge_capacity import BargeCapacityResult
from .checks import Check, all_ok
from .hull import HullGeometry


@dataclass
class JourneyDeratingInputs:
    """A volume-bound barge design + a channel, to be de-rated to a per-journey load."""

    capacity: BargeCapacityResult     # from barge_capacity.compute()

    # Box-hull geometry — MUST match the hull barge_capacity built (zero rakes), so the
    # weight branch and the full-load draft are consistent by construction.
    loa: float
    beam: float
    depth: float
    block_coefficient: float = 0.85
    water_density: float = 1.0        # t/m^3 (1.0 fresh, 1.025 salt)

    # Channel draft cap, kept as depth + UKC so the bookkeeping is explicit (never pass a
    # pre-reduced T_max — that is the silent double-subtract trap).
    design_depth_m: float = 0.0       # channel design depth below min water level
    ukc_m: float = 0.0                # under-keel clearance already in design_depth

    utilisation_floor: float = 0.5    # advisory: below this, the hull is over-built for the channel

    def __post_init__(self):
        if self.loa <= 0 or self.beam <= 0 or self.depth <= 0:
            raise ValueError("loa, beam, depth must be positive")
        if self.design_depth_m < 0 or self.ukc_m < 0:
            raise ValueError("design_depth_m and ukc_m must be non-negative")


@dataclass
class JourneyDeratingResult:
    cargo_capacity_t: float            # echo: volume-bound capacity
    t_max_m: float                     # channel draft cap used (design_depth - UKC)
    full_load_draft_m: float           # echo from barge_capacity
    achievable_tonnage_t: float        # HEADLINE: per-journey payload after de-rating
    binding_limit: str                 # "volume" | "draft"
    volume_utilisation: float          # achievable / capacity (<= 1.0)
    draft_at_achievable_m: float       # draft actually floated
    shed_tonnage_t: float              # capacity - achievable (0 if volume-bound)
    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def compute(inp: JourneyDeratingInputs) -> JourneyDeratingResult:
    """Apply the channel draft cap to a volume-bound barge design."""
    cap = inp.capacity
    cargo_capacity = cap.cargo_capacity_t
    full_load_draft = cap.full_load_draft_m
    lightship = cap.lightship_t

    t_max = max(0.0, inp.design_depth_m - inp.ukc_m)
    hull = HullGeometry(inp.loa, inp.beam, inp.depth, 0, 0, 0, 0)
    cb, rho = inp.block_coefficient, inp.water_density

    if t_max >= full_load_draft:
        # floats fully laden -> volume-bound
        achievable = cargo_capacity
        binding = "volume"
        draft_at = full_load_draft
    else:
        # too deep -> shed cargo until draft = T_max (weight/draft-bound)
        float_draft = min(t_max, inp.depth)          # can't float deeper than the hull
        displacement_at_tmax = cb * hull.displaced_volume(float_draft) * rho
        achievable = max(0.0, min(cargo_capacity, displacement_at_tmax - lightship))
        binding = "draft"
        draft_at = t_max

    utilisation = achievable / cargo_capacity if cargo_capacity > 0 else 0.0
    shed = max(0.0, cargo_capacity - achievable)

    checks = [
        Check("capacity_is_volume_bound", not cap.overloaded,
              "input capacity must be a feasible volume-bound design (not overloaded)"),
        Check("floats", achievable > 0,
              f"channel must float some cargo (T_max {t_max:.2f} m vs lightship draft)"),
        Check("ukc_consistent", inp.design_depth_m >= inp.ukc_m,
              "design depth must be >= UKC (pass depth + UKC, never a pre-reduced T_max)"),
        Check("utilisation_reasonable", utilisation >= inp.utilisation_floor,
              f"volume utilisation {utilisation:.0%} >= floor {inp.utilisation_floor:.0%}",
              severity="warning"),
    ]
    warnings = []
    if binding == "draft":
        warnings.append(
            f"Draft-bound: shed {shed:.0f} t of {cargo_capacity:.0f} t volume capacity "
            f"to float at T_max = {t_max:.2f} m (full-load draft {full_load_draft:.2f} m)."
        )

    return JourneyDeratingResult(
        cargo_capacity_t=cargo_capacity,
        t_max_m=t_max,
        full_load_draft_m=full_load_draft,
        achievable_tonnage_t=achievable,
        binding_limit=binding,
        volume_utilisation=utilisation,
        draft_at_achievable_m=draft_at,
        shed_tonnage_t=shed,
        checks=checks,
        warnings=warnings,
    )
