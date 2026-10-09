"""The calibration pass runs end to end and covers every case in cases.yaml."""
import yaml

from vessel_designer.calibration import CAL, report


def test_report_covers_every_case():
    text = report()
    for c in yaml.safe_load((CAL / "cases.yaml").read_text())["dry_barge"]:
        assert c["id"] in text
    assert "–" not in text.split("## 3.")[1].split("| Ratio |")[1].replace("|---", "")
