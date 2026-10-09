"""Bottom-up ATB unit cost (cargo barge + electric pusher tug) — from the mass model.

Takes the engine's own mass build-up (BargeCalculator: hull plating areas -> steel
tonnes; ASME/IGC pressure-vessel shell -> tank tonnes) and applies fabrication rates,
so the cost is quantity-based rather than a lump allowance. Scope: steel, the cryogenic
(Type-C) tanks and cargo handling; EXCLUDES reliquefaction and nitrogen plant
(pressure-accumulation service, with shore support at the terminals).

RATES ARE DATA, NOT CODE. This module holds no prices. Supply your own as a
``BargeCostRates`` object, a mapping, or a path to a rates file (same keys as the example
file). With no rates given, ``compute`` uses ``barge_cost_rates.example.yaml``: round,
illustrative numbers for the worked example only — not market quotes.

The rates file is flat YAML (``key: value  # comment``). The core reads that subset with the
standard library so it stays free of third-party imports; nested YAML is rejected loudly.

Pure Python (Pyodide-safe).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from importlib import resources
from os import PathLike
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

from .checks import Check, all_ok

EXAMPLE_RATES_FILE = "barge_cost_rates.example.yaml"


@dataclass
class BargeCostInputs:
    # --- masses from the mass model (BargeCalculator weights/tanks; t) ---
    hull_steel_t: float = 253.2          # plating + internal structure
    wing_plate_t: float = 40.3
    weather_shield_t: float = 50.1
    tank_shell_t: float = 215.6          # Type-C cylinders + heads (25 mm, LT steel)
    tank_supports_t: float = 64.7        # saddles, anti-flotation, internals
    insulation_t: float = 25.9           # sprayed PU foam system
    piping_machinery_t: float = 32.9
    outfitting_t: float = 28.8

    # --- electric pusher tug (16 m pusher, modular swappable energy containers) ---
    tug_hull_steel_t: float = 115.0        # 16 m pusher, denser structure — ESTIMATE
    battery_kwh: float = 620.0             # sized on the longest inter-charge leg
    propulsion_kw: float = 230.0           # installed (binding P_bat x 1.2)


@dataclass(frozen=True)
class BargeCostRates:
    """Fabrication / supply rates. No defaults: every rate comes from data you supply."""
    hull_steel_rate: float               # per t of hull steel (barge and tug)
    tank_shell_rate: float               # per t of Type-C tank shell
    tank_supports_rate: float            # per t
    insulation_rate: float               # per t equivalent
    piping_rate: float                   # per t of piping + machinery
    outfitting_rate: float               # per t
    cargo_system_lump: float             # per unit (no reliquefaction, no nitrogen plant)
    paint_anodes_misc: float             # per unit
    battery_rate_per_kwh: float
    propulsion_rate_per_kw: float
    wheelhouse_accom_lump: float         # per tug
    tug_outfitting_lump: float           # per tug
    yard_margin_fraction: float          # fraction of barge + tug subtotal
    delivery_lump: float                 # per ATB unit
    currency: str = "USD"

    @classmethod
    def from_mapping(cls, data: Mapping) -> "BargeCostRates":
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - names)
        if unknown:
            raise ValueError(f"unknown barge cost rate key(s): {unknown}")
        missing = sorted(n for n in names - set(data) if n != "currency")
        if missing:
            raise ValueError(f"missing barge cost rate key(s): {missing}")
        return cls(**{k: (str(v) if k == "currency" else float(v)) for k, v in data.items()})


RatesLike = Union[BargeCostRates, Mapping, str, PathLike, None]


def _example_rates_text() -> str:
    """The shipped example: package data when installed, the repo's examples/ when run from source."""
    pkg = resources.files("vessel_designer").joinpath("data", EXAMPLE_RATES_FILE)
    if pkg.is_file():
        return pkg.read_text(encoding="utf-8")
    repo = Path(__file__).resolve().parents[3] / "examples" / EXAMPLE_RATES_FILE
    if repo.is_file():
        return repo.read_text(encoding="utf-8")
    raise FileNotFoundError(f"{EXAMPLE_RATES_FILE} not found; pass rates explicitly")


def parse_flat_yaml(text: str) -> Dict[str, str]:
    """``key: value`` lines, ``#`` comments and blank lines; anything else is an error."""
    out: Dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip().strip("'\"")
        if not sep or not key or not value or raw[:1].isspace() or not key.isidentifier():
            raise ValueError(f"rates file line {n}: expected flat 'key: value', got {raw!r}")
        if key in out:
            raise ValueError(f"rates file line {n}: duplicate key {key!r}")
        out[key] = value
    return out


def load_rates(rates: RatesLike = None) -> BargeCostRates:
    """Rates from an object, a mapping, or a YAML path. None -> the illustrative example file."""
    if isinstance(rates, BargeCostRates):
        return rates
    if isinstance(rates, Mapping):
        return BargeCostRates.from_mapping(rates)
    text = _example_rates_text() if rates is None else Path(rates).read_text(encoding="utf-8")
    return BargeCostRates.from_mapping(parse_flat_yaml(text))


@dataclass
class BargeCostResult:
    barge_breakdown: Dict[str, float]
    tug_breakdown: Dict[str, float]
    barge_subtotal: float
    tug_subtotal: float
    yard_margin: float
    delivery: float
    unit_total: float                      # one ATB unit (barge + tug), delivered
    checks: List[Check] = field(default_factory=list)
    rates: Optional[BargeCostRates] = None   # the rates this result was priced with

    @property
    def ok(self) -> bool:
        return all_ok(self.checks)


def compute(inp: BargeCostInputs, rates: RatesLike = None) -> BargeCostResult:
    """Unit cost from the masses in ``inp`` and the ``rates`` you supply (see ``load_rates``)."""
    rt = load_rates(rates)
    barge = {
        "hull_steel": (inp.hull_steel_t + inp.wing_plate_t + inp.weather_shield_t) * rt.hull_steel_rate,
        "type_c_tanks": inp.tank_shell_t * rt.tank_shell_rate,
        "tank_supports": inp.tank_supports_t * rt.tank_supports_rate,
        "insulation": inp.insulation_t * rt.insulation_rate,
        "cargo_system": rt.cargo_system_lump,
        "piping_machinery": inp.piping_machinery_t * rt.piping_rate,
        "outfitting": inp.outfitting_t * rt.outfitting_rate,
        "paint_anodes_misc": rt.paint_anodes_misc,
    }
    tug = {
        "hull_steel": inp.tug_hull_steel_t * rt.hull_steel_rate,
        "battery": inp.battery_kwh * rt.battery_rate_per_kwh,
        "propulsion": inp.propulsion_kw * rt.propulsion_rate_per_kw,
        "wheelhouse_accommodation": rt.wheelhouse_accom_lump,
        "outfitting": rt.tug_outfitting_lump,
    }
    b_sub, t_sub = sum(barge.values()), sum(tug.values())
    margin = rt.yard_margin_fraction * (b_sub + t_sub)
    total = b_sub + t_sub + margin + rt.delivery_lump

    checks = [
        Check("masses_positive", min(inp.hull_steel_t, inp.tank_shell_t) > 0,
              "mass-model inputs present"),
        Check("no_reliquefaction_in_scope", True,
              "cargo system excludes reliquefaction and nitrogen plant per the "
              "pressure-accumulation operating concept",
              severity="warning"),
        Check("fabrication_rates_are_estimates", False,
              "fabrication/supply rates are user-supplied estimates; replace them with "
              "yard quotes before relying on the total",
              severity="warning"),
    ]
    return BargeCostResult(
        barge_breakdown={k: round(v) for k, v in barge.items()},
        tug_breakdown={k: round(v) for k, v in tug.items()},
        barge_subtotal=round(b_sub), tug_subtotal=round(t_sub),
        yard_margin=round(margin), delivery=rt.delivery_lump, rates=rt,
        unit_total=round(total), checks=checks,
    )
