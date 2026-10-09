"""Cargo properties for LNG and LPG variants."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class CargoProperties:
    """Physical properties of a liquid gas cargo."""

    name: str
    density: float          # kg/m^3 (liquid density for gas; stowage density for dry bulk)
    temperature: float      # Storage temperature (deg C)
    pressure: float         # Storage pressure (barg)
    description: str = ""
    phase: str = "liquid_gas"  # "liquid_gas" (cryogenic tanks) or "dry_bulk" (hopper hold)


CARGO_DATABASE: Dict[str, CargoProperties] = {
    "LNG": CargoProperties(
        name="LNG",
        density=450.0,
        temperature=-162.0,
        pressure=0.25,
        description="Liquefied Natural Gas (methane-rich)",
    ),
    "LNG_ethane": CargoProperties(
        name="LNG / Ethane",
        density=500.0,
        temperature=-162.0,
        pressure=0.25,
        description="LNG–ethane blend at cryogenic temperature",
    ),
    "LPG_propane": CargoProperties(
        name="LPG (Propane)",
        # 581 kg/m3 = saturated liquid propane at its normal boiling point, -42.1 C,
        # near-atmospheric. This is the FULLY REFRIGERATED case, which is the design basis
        # (Niall, 2026-09-16: "assume we are carrying cryogenic propane").
        #
        # It was 500.0, and revenue.py carried 493.0, BOTH labelled -42 C. Neither is a
        # refrigerated density: 489-493 kg/m3 is propane at about +25 C, i.e. the
        # pressurised-ambient case. The catalogue had taken the tank design from one storage
        # regime and the density from the other, and every gas tonnage the model produced was
        # 16.2% light as a result.
        #
        # The regime is not just a number: fully refrigerated means -42 C at near-atmospheric
        # pressure, with insulation and reliquefaction, against thick-walled vessels at ~8 barg
        # for ambient storage. Confirm the cargo spec with the shipper.
        # Sources: NIST WebBook; Air Liquide Gas Encyclopedia; Engineering ToolBox.
        density=581.0,
        temperature=-42.1,
        pressure=0.0,
        description="Fully refrigerated liquefied propane (-42.1 C, near-atmospheric)",
    ),
    "LPG_butane": CargoProperties(
        name="LPG (Butane)",
        density=600.0,
        temperature=-1.0,
        pressure=0.0,
        description="Cryogenic liquefied butane",
    ),
    "LPG_mix": CargoProperties(
        name="LPG (60/40 Propane/Butane)",
        # 588.4 = harmonic (volume-additive) blend of 60% propane at 581 and 40% butane at
        # 601, by mass: 1/rho = 0.6/581 + 0.4/601. Was 530.0, which was the same
        # ambient-temperature error as LPG_propane carried. LPG_butane (600) was already
        # right. Confirm the actual cargo and composition with the shipper.
        density=588.4,
        temperature=-42.1,
        pressure=0.0,
        description="Fully refrigerated LPG mix (60% propane / 40% butane by mass)",
    ),
    "bauxite": CargoProperties(
        name="Bauxite",
        density=1500.0,
        temperature=20.0,
        pressure=0.0,
        description="Dry bulk bauxite ore (stowage density, ~0.67 m3/t)",
        phase="dry_bulk",
    ),
}


def get_cargo(cargo_type: str) -> CargoProperties:
    """Look up cargo properties by type key."""
    if cargo_type not in CARGO_DATABASE:
        valid = ", ".join(CARGO_DATABASE.keys())
        raise ValueError(f"Unknown cargo type '{cargo_type}'. Valid types: {valid}")
    return CARGO_DATABASE[cargo_type]
