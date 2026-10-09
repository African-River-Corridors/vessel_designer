"""Store a calibration source document in a private S3 bucket and register it (ADR 0001).

    python3 tools/store_source.py FILE --group standards/GB38030 --url URL --title "..." \
        --licence "..." [--note "..."]

Uploads to s3://$VESSEL_DESIGNER_SOURCES_BUCKET/sources/<group>/<sha256>.<ext> and appends a
record (with the object key, not the bucket) to calibration/sources.yaml. Re-storing the same
file is a no-op. The file itself never enters git. Needs the AWS CLI and a live session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "calibration" / "sources.yaml"
BUCKET_ENV = "VESSEL_DESIGNER_SOURCES_BUCKET"


def bucket() -> str:
    b = os.environ.get(BUCKET_ENV, "").strip()
    if not b:
        raise SystemExit(f"set {BUCKET_ENV} to the name of your private sources bucket")
    return b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--group", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--licence", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    sha = hashlib.sha256(a.file.read_bytes()).hexdigest()
    reg = yaml.safe_load(REGISTER.read_text()) if REGISTER.exists() else {"sources": []}
    if any(s["sha256"] == sha for s in reg["sources"]):
        print(f"already stored: {sha}")
        return
    key = f"sources/{a.group}/{sha}{a.file.suffix.lower()}"
    b = bucket()
    subprocess.run(["aws", "s3", "cp", str(a.file), f"s3://{b}/{key}", "--only-show-errors"],
                   check=True)
    reg["sources"].append({
        "sha256": sha, "key": key, "title": a.title, "url": a.url,
        "original_name": a.file.name, "bytes": a.file.stat().st_size,
        "stored": dt.date.today().isoformat(), "licence": a.licence, "note": a.note,
    })
    REGISTER.write_text("# Calibration source documents (files live in S3, ADR 0001).\n"
                        + yaml.safe_dump(reg, sort_keys=False, allow_unicode=True, width=110))
    print(f"stored {a.file.name} -> s3://{b}/{key}")


if __name__ == "__main__":
    main()
