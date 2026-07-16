#!/usr/bin/env python3
"""Verify the generated publication PDF's structure, metadata, and core text."""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "output" / "pdf" / "clinical_documentation_copilot_research_report.pdf"
EXPECTED_TITLE = "Clinical Documentation Copilot"
EXPECTED_AUTHOR = "Manideep"
EXPECTED_PAGES = 24


def main() -> int:
    errors: list[str] = []
    if not REPORT.exists():
        print(f"Missing report: {REPORT}")
        return 1
    reader = PdfReader(REPORT)
    metadata = reader.metadata or {}
    if len(reader.pages) != EXPECTED_PAGES:
        errors.append(f"Expected {EXPECTED_PAGES} pages; found {len(reader.pages)}")
    if metadata.get("/Author") != EXPECTED_AUTHOR:
        errors.append(f"Expected sole PDF author {EXPECTED_AUTHOR!r}; found {metadata.get('/Author')!r}")
    if EXPECTED_TITLE not in str(metadata.get("/Title", "")):
        errors.append("PDF title metadata is missing the project title")

    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    if any(len(text) < 150 for text in page_texts):
        errors.append("At least one page has insufficient extractable text")
    document_text = "\n".join(page_texts)
    required = [
        "April 18, 2026",
        "July 16, 2026",
        "2,837,098",
        "Clinical Documentation Copilot",
        "Limitations, roadmap, and conclusion",
        "Author: Manideep",
    ]
    for phrase in required:
        if phrase not in document_text:
            errors.append(f"Missing required report text: {phrase}")
    if "PRE-RELEASE PLACEHOLDER" in document_text:
        errors.append("Report still contains a pre-release evidence placeholder")

    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if round(width, 1) != 612.0 or round(height, 1) != 792.0:
            errors.append(f"Page {page_number} is not US Letter size: {width} x {height}")

    if errors:
        print("Report verification failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"Verified {REPORT}: 24 US Letter pages, Manideep author metadata, required text, and no placeholders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
