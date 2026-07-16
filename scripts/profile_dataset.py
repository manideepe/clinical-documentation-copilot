#!/usr/bin/env python3
"""Stream-profile Synthea CSV files and emit auditable row-count evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLINICAL_FACT_TABLES = {
    "allergies.csv",
    "careplans.csv",
    "conditions.csv",
    "devices.csv",
    "encounters.csv",
    "imaging_studies.csv",
    "immunizations.csv",
    "medications.csv",
    "observations.csv",
    "procedures.csv",
    "supplies.csv",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_profile(path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration:
            header = []
            rows = 0
        else:
            rows = sum(1 for _ in reader)
    return {
        "file": path.name,
        "rows": rows,
        "columns": len(header),
        "column_names": header,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "profile_seconds": round(time.perf_counter() - started, 4),
    }


def locate_csvs(root: Path) -> list[Path]:
    base = root / "data" / "raw" / "synthea-covid19-10k"
    return sorted(p for p in base.rglob("*.csv") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--minimum-rows", type=int, default=1_000_000)
    args = parser.parse_args()

    csvs = locate_csvs(args.root)
    if not csvs:
        print("No CSV files found. Run scripts/download_synthea.py first.", file=sys.stderr)
        return 2

    started = time.perf_counter()
    profiles = [csv_profile(path) for path in csvs]
    total_rows = sum(item["rows"] for item in profiles)
    clinical_fact_rows = sum(
        item["rows"] for item in profiles if item["file"] in CLINICAL_FACT_TABLES
    )
    patient_count = next(
        (item["rows"] for item in profiles if item["file"] == "patients.csv"), 0
    )
    manifest = {
        "benchmark": "MITRE Synthea COVID-19 10K CSV",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "definition": "Sum of data rows across extracted Synthea CSV relation files; headers excluded.",
        "synthetic_data_only": True,
        "minimum_required_clinical_fact_rows": args.minimum_rows,
        "patient_count": patient_count,
        "clinical_fact_tables": sorted(CLINICAL_FACT_TABLES),
        "clinical_fact_rows": clinical_fact_rows,
        "all_csv_rows": total_rows,
        "total_rows": total_rows,
        "threshold_passed": clinical_fact_rows >= args.minimum_rows,
        "file_count": len(profiles),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "files": profiles,
    }

    processed = args.root / "data" / "processed" / "dataset_manifest.json"
    evidence_json = args.root / "evidence" / "dataset" / "row_counts.json"
    evidence_csv = args.root / "evidence" / "dataset" / "row_counts.csv"
    for path in (processed, evidence_json, evidence_csv):
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    processed.write_text(payload, encoding="utf-8")
    evidence_json.write_text(payload, encoding="utf-8")
    with evidence_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file", "rows", "columns", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows({key: item[key] for key in writer.fieldnames} for item in profiles)

    print(json.dumps({
        "patient_count": patient_count,
        "clinical_fact_rows": clinical_fact_rows,
        "all_csv_rows": total_rows,
        "file_count": len(profiles),
        "threshold_passed": manifest["threshold_passed"],
        "manifest": str(processed),
    }, indent=2))
    return 0 if manifest["threshold_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
