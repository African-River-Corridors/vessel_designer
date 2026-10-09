"""Test triad for barge_cost (bottom-up ATB unit cost).

Tests price with explicit, round TEST rates so the arithmetic is checkable by hand. The module
holds no prices of its own; the shipped example file is illustrative only.
"""
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from vessel_designer.core.barge_cost import (EXAMPLE_RATES_FILE, BargeCostInputs, BargeCostRates,
                                             compute, load_rates)

RATES = BargeCostRates(
    hull_steel_rate=1000.0, tank_shell_rate=1000.0, tank_supports_rate=1000.0,
    insulation_rate=1000.0, piping_rate=1000.0, outfitting_rate=1000.0,
    cargo_system_lump=100_000.0, paint_anodes_misc=100_000.0,
    battery_rate_per_kwh=100.0, propulsion_rate_per_kw=1000.0,
    wheelhouse_accom_lump=100_000.0, tug_outfitting_lump=100_000.0,
    yard_margin_fraction=0.10, delivery_lump=50_000.0,
)
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / EXAMPLE_RATES_FILE


def test_golden_base_case():
    r = compute(BargeCostInputs(), RATES)
    assert r.barge_subtotal == 911_500       # 811.5 t x 1,000 + two 100,000 lumps
    assert r.tug_subtotal == 607_000         # 115 t x 1,000 + 620 kWh x 100 + 230 kW x 1,000 + 200,000
    assert r.unit_total == 1_720_350         # + 10 % margin + 50,000 delivery


def test_property_monotone_in_steel():
    lo = compute(BargeCostInputs(hull_steel_t=200.0), RATES)
    hi = compute(BargeCostInputs(hull_steel_t=300.0), RATES)
    assert hi.unit_total > lo.unit_total
    assert hi.barge_breakdown["hull_steel"] > lo.barge_breakdown["hull_steel"]


def test_property_margin_scales():
    base = compute(BargeCostInputs(), replace(RATES, yard_margin_fraction=0.0))
    plus = compute(BargeCostInputs(), replace(RATES, yard_margin_fraction=0.20))
    assert abs(plus.unit_total - (base.unit_total + 0.20 * (base.barge_subtotal + base.tug_subtotal))) < 2.0


def test_feasibility_checks():
    r = compute(BargeCostInputs(), RATES)
    names = {c.name for c in r.checks}
    assert {"masses_positive", "no_reliquefaction_in_scope", "fabrication_rates_are_estimates"} <= names
    assert r.ok  # warnings don't gate


def test_rates_from_mapping_and_path_match_the_object(tmp_path):
    data = {k: v for k, v in RATES.__dict__.items()}
    path = tmp_path / "rates.yaml"
    path.write_text(yaml.safe_dump(data))
    ref = compute(BargeCostInputs(), RATES).unit_total
    assert compute(BargeCostInputs(), data).unit_total == ref
    assert compute(BargeCostInputs(), str(path)).unit_total == ref
    assert compute(BargeCostInputs(), path).rates == RATES


def test_default_rates_are_the_shipped_example_file():
    """No rates given -> the illustrative example file, read through the package loader."""
    from_file = BargeCostRates.from_mapping(yaml.safe_load(EXAMPLE.read_text()))
    assert load_rates() == from_file
    assert compute(BargeCostInputs()).unit_total == compute(BargeCostInputs(), from_file).unit_total


def test_example_file_says_it_is_illustrative():
    first = EXAMPLE.read_text(encoding="utf-8").splitlines()[0]
    assert "Illustrative rates for the example only" in first and "supply your own" in first


def test_bad_rates_are_rejected():
    with pytest.raises(ValueError, match="missing"):
        BargeCostRates.from_mapping({"hull_steel_rate": 1.0})
    with pytest.raises(ValueError, match="unknown"):
        BargeCostRates.from_mapping({**RATES.__dict__, "hull_steel_rte": 1.0})


def test_flat_reader_agrees_with_pyyaml_on_the_example_and_rejects_nesting(tmp_path):
    from vessel_designer.core.barge_cost import parse_flat_yaml
    text = EXAMPLE.read_text(encoding="utf-8")
    assert BargeCostRates.from_mapping(parse_flat_yaml(text)) == \
        BargeCostRates.from_mapping(yaml.safe_load(text))
    nested = tmp_path / "nested.yaml"
    nested.write_text("rates:\n  hull_steel_rate: 1\n")
    with pytest.raises(ValueError, match="flat"):
        load_rates(nested)
