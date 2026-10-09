"""Build the static web simulator's data and Python wheel into web/.

    python3 tools/build_web.py

web/ is then a self-contained static site: index.html + app.js + style.css + assets/ +
data/*.json + wheels/*.whl. The browser runs the real Python core through Pyodide, so the
page and the engineering cannot drift apart. Publishes nothing.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import tempfile
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


# The page is public. Internal references (local paths, private project names) never ship.
PRIVATE = ("/users/", "ankobra", "vessel_standards.py", "niallsankofa", "genser")


def public_source(src: str) -> str:
    """Keep the published citations in a source string; drop internal provenance clauses."""
    src = src.split(", as transcribed in ")[0]
    keep = [part.strip() for part in src.split(";") if not any(w in part.lower() for w in PRIVATE)]
    return "; ".join(keep)


CODE_PRIVATE = re.compile(r"ankobra|benin|genser|niall|q-ank|dec-20\d\d|edikan|tarkwa|chirano|/users/",
                          re.IGNORECASE)


def strip_source(text: str) -> str:
    """Drop comments and docstrings: the core's notes carry internal project history."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body[0] = ast.Expr(ast.Constant(""))
    return ast.unparse(tree) + "\n"


def build_public_wheel(out: Path) -> None:
    """Wheel of the package with comments/docstrings stripped; refuses to build on a leak."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for meta in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):   # pyproject names them
            shutil.copy(ROOT / meta, tmp)
        for f in (ROOT / "src").rglob("*.py"):
            if f.name == "calibration.py":
                continue                       # reads local files; not needed in the browser
            dst = tmp / f.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            code = strip_source(f.read_text())
            hits = sorted({m.group(0).lower() for m in CODE_PRIVATE.finditer(code)})
            if hits:
                raise SystemExit(f"refusing to publish: {f.name} still contains {hits}")
            dst.write_text(code)
        # package data the wheel force-includes (see pyproject.toml)
        ex = tmp / "examples" / "barge_cost_rates.example.yaml"
        ex.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "examples" / ex.name, ex)
        subprocess.run(["uv", "build", "--wheel", "-o", str(out), str(tmp)], check=True,
                       capture_output=True)


def main() -> None:
    wheels = WEB / "wheels"
    shutil.rmtree(wheels, ignore_errors=True)
    build_public_wheel(wheels)
    whl = next(wheels.glob("*.whl")).name

    cat = ROOT / "catalogue"
    classes = {c["id"]: c for c in yaml.safe_load((cat / "vessel_classes.yaml").read_text())["classes"]}
    ws = yaml.safe_load((cat / "working_set.yaml").read_text())
    vessels = {v["id"]: v for v in yaml.safe_load((cat / "reference_vessels.yaml").read_text())["vessels"]}

    def rng(x):
        return x if isinstance(x, list) else ([x, x] if x is not None else None)

    out = []
    for cid in ws["hulls"]:
        c = classes[cid]
        out.append({
            "id": cid, "family": c["family"], "formation": c["formation"],
            "cargo_modes": c.get("cargo_modes") or [], "loa_m": rng(c.get("loa_m")),
            "beam_m": rng(c.get("beam_m")), "draught_m": rng(c.get("draught_m")),
            "dwt_t": rng(c.get("dwt_t")), "source": public_source(c.get("source", "")),
            "confidence": c.get("confidence"),
            "reference_vessels": [{"name": vessels[v].get("name"), "loa_m": vessels[v].get("loa_m"),
                                   "beam_m": vessels[v].get("beam_m"), "dwt_t": vessels[v].get("dwt_t")}
                                  for v in c.get("reference_vessels", []) if v in vessels],
        })
    data = WEB / "data"
    data.mkdir(exist_ok=True)
    text = json.dumps(out, indent=1, ensure_ascii=False)
    leaks = [w for w in PRIVATE if w in text.lower()]
    if leaks:
        raise SystemExit(f"refusing to publish: private references {leaks} in classes.json")
    (data / "classes.json").write_text(text)
    f = yaml.safe_load((ROOT / "calibration" / "factors.yaml").read_text())
    (data / "factors.json").write_text(json.dumps({
        "box_k": f["lightship_k_t_per_m3"]["box"],
        "box_cb": f["block_coefficient_box_barge_on_loa"]}, indent=1))
    (data / "build.json").write_text(json.dumps({"wheel": whl}))
    print(f"web/: {whl}, {len(out)} hull classes")


if __name__ == "__main__":
    main()
