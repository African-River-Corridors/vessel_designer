"""The README's worked example runs."""
import runpy
from pathlib import Path


def test_quickstart_runs(capsys):
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples" / "quickstart.py"),
                   run_name="__main__")
    out = capsys.readouterr().out
    assert "Searched   : 1 tank(s) abreast" in out and "2,058 t" in out
