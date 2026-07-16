#!/usr/bin/env python3
"""Validate high-value integrity properties of the extracted Synthea CSV set."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Iterable


EVIDENCE_SNAPSHOT_AT = "2026-04-18T17:00:00+00:00"


def only_csv_dir(root: Path) -> Path:
    base = root / "data" / "raw" / "synthea-covid19-10k"
    candidates = [path.parent for path in base.rglob("patients.csv")]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one patients.csv, found {len(candidates)}")
    return candidates[0]


def load_ids(path: Path) -> tuple[set[str], int]:
    values: set[str] = set()
    duplicates = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            value = row["Id"]
            if value in values:
                duplicates += 1
            values.add(value)
    return values, duplicates


def rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    started = time.perf_counter()
    base = only_csv_dir(args.root)

    patient_ids, duplicate_patients = load_ids(base / "patients.csv")
    encounter_ids, duplicate_encounters = load_ids(base / "encounters.csv")
    organization_ids, duplicate_organizations = load_ids(base / "organizations.csv")
    provider_ids, duplicate_providers = load_ids(base / "providers.csv")

    violations: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    checked_rows = 0
    patient_fk_rows = 0
    encounter_fk_rows = 0
    temporal_rows = 0

    for path in sorted(base.glob("*.csv")):
        for row in rows(path):
            checked_rows += 1
            if "PATIENT" in row and row["PATIENT"]:
                patient_fk_rows += 1
                if row["PATIENT"] not in patient_ids:
                    violations[f"{path.name}:missing_patient"] += 1
            if "ENCOUNTER" in row and row["ENCOUNTER"]:
                encounter_fk_rows += 1
                if row["ENCOUNTER"] not in encounter_ids:
                    violations[f"{path.name}:missing_encounter"] += 1
            if "START" in row and "STOP" in row and row["START"] and row["STOP"]:
                temporal_rows += 1
                if row["STOP"] < row["START"]:  # ISO dates/timestamps preserve ordering
                    # Upstream synthetic-data quality issue: preserve and report rather
                    # than silently rewriting source records. Production ingestion would
                    # quarantine these rows according to its data-quality policy.
                    warnings[f"{path.name}:stop_before_start"] += 1
            if path.name == "encounters.csv":
                if row["ORGANIZATION"] and row["ORGANIZATION"] not in organization_ids:
                    violations["encounters.csv:missing_organization"] += 1
                if row["PROVIDER"] and row["PROVIDER"] not in provider_ids:
                    violations["encounters.csv:missing_provider"] += 1

    uniqueness = {
        "patients_duplicate_ids": duplicate_patients,
        "encounters_duplicate_ids": duplicate_encounters,
        "organizations_duplicate_ids": duplicate_organizations,
        "providers_duplicate_ids": duplicate_providers,
    }
    passed = not violations and all(value == 0 for value in uniqueness.values())
    report = {
        "benchmark": "MITRE Synthea COVID-19 10K CSV",
        "evidence_snapshot_at_utc": EVIDENCE_SNAPSHOT_AT,
        "status": "passed_with_warnings" if passed and warnings else "passed" if passed else "failed",
        "passed": passed,
        "checked_rows": checked_rows,
        "patient_count": len(patient_ids),
        "encounter_count": len(encounter_ids),
        "patient_foreign_keys_checked": patient_fk_rows,
        "encounter_foreign_keys_checked": encounter_fk_rows,
        "temporal_ranges_checked": temporal_rows,
        "uniqueness": uniqueness,
        "violations": dict(sorted(violations.items())),
        "warnings": dict(sorted(warnings.items())),
        "warning_policy": "Source anomalies are preserved and reported; operational ingestion should quarantine them.",
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
    destination = args.root / "evidence" / "dataset" / "integrity_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
