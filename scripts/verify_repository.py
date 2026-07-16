#!/usr/bin/env python3
"""Fail-fast structural checks for release evidence and prohibited files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "backend",
    "frontend",
    "docs",
    "evidence/dataset/row_counts.json",
    "evidence/dataset/integrity_report.json",
    "evidence/tests/test_inventory.json",
    "evidence/tests/test_summary.json",
    "evidence/tests/performance_results.json",
    "evidence/screenshots/active-plan-workflow.png",
    "evidence/screenshots/expired-plan-safety-gate.png",
    "output/pdf/clinical_documentation_copilot_research_report.pdf",
]
PROHIBITED_SUFFIXES = {".wav", ".mp3", ".m4a", ".sqlite", ".db", ".pem", ".key"}


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).exists():
            errors.append(f"Missing required artifact: {relative}")

    manifest_path = ROOT / "evidence" / "dataset" / "row_counts.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("clinical_fact_rows", 0) < 1_000_000 or not manifest.get("threshold_passed"):
            errors.append("Dataset evidence does not prove at least 1,000,000 clinical-fact rows")

    integrity_path = ROOT / "evidence" / "dataset" / "integrity_report.json"
    if integrity_path.exists():
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        if not integrity.get("passed"):
            errors.append("Dataset integrity evidence is not passing")

    test_path = ROOT / "evidence" / "tests" / "test_inventory.json"
    if test_path.exists():
        test_inventory = json.loads(test_path.read_text(encoding="utf-8"))
        if not test_inventory.get("passed"):
            errors.append("Automated release evidence is not passing")
        if test_inventory.get("summary", {}).get("failed_records"):
            errors.append("Automated release evidence contains failed records")

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if "data/raw" in relative.as_posix() or "node_modules" in relative.parts or ".venv" in relative.parts:
            continue
        if path.suffix.lower() in PROHIBITED_SUFFIXES:
            errors.append(f"Potential secret/recording/database must not be committed: {relative}")

    if errors:
        print("Repository verification failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Repository structure, dataset threshold, and prohibited-file checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
