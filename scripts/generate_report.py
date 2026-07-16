#!/usr/bin/env python3
"""Generate the Clinical Documentation Copilot research report.

The report is intentionally evidence-driven. Dataset measurements, integrity
findings, source receipts, CSV profiles, the research reference register, and an
optional automated-test inventory are read from the repository at build time.
No test outcome is inferred from source files or from the presence of tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepInFrame, Paragraph, Spacer, Table, TableStyle


REPORT_TITLE = "Clinical Documentation Copilot"
REPORT_SUBTITLE = "A Safety-First Reference Architecture for Grounded Clinical Documentation"
AUTHOR = "Manideep"
PUBLICATION_DATE = "April 18, 2026"
EVIDENCE_REFRESH_DATE = "April 18, 2026"
TOTAL_PAGES = 31
DEFAULT_OUTPUT = Path("output/pdf/clinical_documentation_copilot_research_report.pdf")

PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT = 0.72 * inch
RIGHT = 0.72 * inch
TOP = 0.82 * inch
BOTTOM = 0.70 * inch
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT
CONTENT_TOP = PAGE_HEIGHT - TOP
CONTENT_BOTTOM = BOTTOM
CONTENT_HEIGHT = CONTENT_TOP - CONTENT_BOTTOM

INK = HexColor("#17202A")
ACCENT = HexColor("#263746")
MID = HexColor("#5E6871")
RULE = HexColor("#AEB6BD")
PALE = HexColor("#EEF1F3")
PALE_2 = HexColor("#F7F8F9")
WHITE = colors.white
WARN = HexColor("#6B4F20")


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=31,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=13.5,
            leading=18,
            textColor=ACCENT,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=21,
            textColor=INK,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=ACCENT,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontName="Times-Roman",
            fontSize=9.4,
            leading=13.0,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=7,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            parent=sample["BodyText"],
            fontName="Times-Roman",
            fontSize=8.2,
            leading=10.8,
            textColor=INK,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=sample["BodyText"],
            fontName="Times-Roman",
            fontSize=8.9,
            leading=11.9,
            leftIndent=12,
            firstLineIndent=-8,
            bulletIndent=0,
            textColor=INK,
            spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=sample["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=7.2,
            leading=9,
            textColor=MID,
            spaceBefore=3,
            spaceAfter=5,
        ),
        "table": ParagraphStyle(
            "TableBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.2,
            textColor=INK,
        ),
        "table_small": ParagraphStyle(
            "TableSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=6.4,
            leading=7.8,
            textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=8.6,
            textColor=WHITE,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.6,
            textColor=INK,
            spaceAfter=0,
        ),
        "metric": ParagraphStyle(
            "Metric",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=17,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8.2,
            textColor=MID,
            alignment=TA_CENTER,
        ),
        "reference": ParagraphStyle(
            "Reference",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=6.7,
            leading=8.35,
            textColor=INK,
            leftIndent=13,
            firstLineIndent=-13,
            spaceAfter=5.2,
            splitLongWords=True,
        ),
        "test": ParagraphStyle(
            "TestInventory",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=6.3,
            leading=7.7,
            textColor=INK,
            spaceAfter=0,
        ),
    }


STYLES = _styles()


def safe(value: Any) -> str:
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    normalized = (
        str(value)
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return escape(normalized)


def fmt_int(value: Any, fallback: str = "Not available") -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return fallback


def compact_json(value: Any, limit: int = 280) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class EvidenceBundle:
    project_root: Path
    catalog: dict[str, Any]
    row_counts: dict[str, Any]
    row_count_rows: list[dict[str, Any]]
    integrity: dict[str, Any]
    source_receipt: dict[str, Any]
    references: dict[str, Any]
    test_inventory_path: Path
    tests: list[dict[str, Any]]
    tests_present: bool
    test_inventory_metadata: dict[str, Any]


def _first_list(container: dict[str, Any], keys: Sequence[str]) -> list[Any] | None:
    for key in keys:
        value = container.get(key)
        if isinstance(value, list):
            return value
    return None


def _normalize_test_items(raw: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata: dict[str, Any] = {}
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        selected = _first_list(raw, ("tests", "items", "test_cases", "inventory", "results"))
        if selected is not None:
            items = selected
            metadata = {key: value for key, value in raw.items() if value is not selected}
        else:
            items = []
            for group, value in raw.items():
                if isinstance(value, list):
                    for child in value:
                        if isinstance(child, dict):
                            items.append({"group": group, **child})
                        else:
                            items.append({"group": group, "value": child})
                else:
                    metadata[group] = value
    else:
        items = []
        metadata = {"unparsed_top_level_value": compact_json(raw)}

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            normalized.append(
                {
                    "index": index,
                    "id": f"TEST-{index:03d}",
                    "name": compact_json(item),
                    "status": "not recorded",
                    "description": "",
                    "metadata": "",
                }
            )
            continue
        identifier = next(
            (item[key] for key in ("id", "test_id", "nodeid", "case_id") if item.get(key)),
            f"TEST-{index:03d}",
        )
        name = next(
            (item[key] for key in ("name", "test", "title", "scenario") if item.get(key)),
            identifier,
        )
        status = next(
            (item[key] for key in ("status", "result", "outcome") if item.get(key) is not None),
            "not recorded",
        )
        description = next(
            (
                item[key]
                for key in ("description", "expected", "coverage", "assertion", "purpose")
                if item.get(key)
            ),
            "",
        )
        consumed = {
            "id",
            "test_id",
            "nodeid",
            "case_id",
            "name",
            "test",
            "title",
            "scenario",
            "status",
            "result",
            "outcome",
            "description",
            "expected",
            "coverage",
            "assertion",
            "purpose",
        }
        remainder = {key: value for key, value in item.items() if key not in consumed}
        normalized.append(
            {
                "index": index,
                "id": str(identifier),
                "name": str(name),
                "status": str(status),
                "description": compact_json(description),
                "metadata": compact_json(remainder) if remainder else "",
            }
        )
    return normalized, metadata


def load_evidence(project_root: Path) -> EvidenceBundle:
    evidence_root = project_root / "evidence"
    catalog: dict[str, Any] = {}
    if evidence_root.exists():
        for path in sorted(evidence_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".json", ".csv"}:
                continue
            key = path.relative_to(project_root).as_posix()
            try:
                catalog[key] = read_json(path) if path.suffix.lower() == ".json" else read_csv(path)
            except (OSError, ValueError, csv.Error) as exc:
                catalog[key] = {"load_error": f"{type(exc).__name__}: {exc}"}

    row_counts = catalog.get("evidence/dataset/row_counts.json", {})
    csv_rows = catalog.get("evidence/dataset/row_counts.csv", [])
    if not isinstance(row_counts, dict):
        row_counts = {}
    if not isinstance(csv_rows, list):
        csv_rows = []
    file_rows = row_counts.get("files")
    row_count_rows = file_rows if isinstance(file_rows, list) else csv_rows
    if not row_counts and row_count_rows:
        total = sum(int(row.get("rows", 0) or 0) for row in row_count_rows)
        row_counts = {
            "total_rows": total,
            "all_csv_rows": total,
            "file_count": len(row_count_rows),
            "definition": "Derived from evidence/dataset/row_counts.csv; headers excluded.",
        }

    integrity = catalog.get("evidence/dataset/integrity_report.json", {})
    source_receipt = catalog.get("evidence/dataset/source_receipt.json", {})
    if not isinstance(integrity, dict):
        integrity = {}
    if not isinstance(source_receipt, dict):
        source_receipt = {}

    references_path = project_root / "docs" / "research" / "references.json"
    references = read_json(references_path) if references_path.exists() else {"sources": []}
    if not isinstance(references, dict):
        references = {"sources": []}

    test_path = evidence_root / "tests" / "test_inventory.json"
    tests_present = test_path.exists()
    if tests_present:
        try:
            tests, test_meta = _normalize_test_items(read_json(test_path))
        except (OSError, ValueError) as exc:
            tests = []
            test_meta = {"load_error": f"{type(exc).__name__}: {exc}"}
    else:
        tests = []
        test_meta = {}

    return EvidenceBundle(
        project_root=project_root,
        catalog=catalog,
        row_counts=row_counts,
        row_count_rows=[row for row in row_count_rows if isinstance(row, dict)],
        integrity=integrity,
        source_receipt=source_receipt,
        references=references,
        test_inventory_path=test_path,
        tests=tests,
        tests_present=tests_present,
        test_inventory_metadata=test_meta,
    )


class PageLayout:
    def __init__(self, canvas: Canvas, page_number: int, section: str):
        self.canvas = canvas
        self.page_number = page_number
        self.section = section
        self.x = LEFT
        self.y = CONTENT_TOP
        self.width = CONTENT_WIDTH

    @property
    def remaining(self) -> float:
        return self.y - CONTENT_BOTTOM

    def header_footer(self) -> None:
        c = self.canvas
        c.saveState()
        c.setFillColor(WHITE)
        c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.45)
        c.line(LEFT, PAGE_HEIGHT - 0.48 * inch, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 0.48 * inch)
        c.setFont("Helvetica-Bold", 6.7)
        c.setFillColor(ACCENT)
        c.drawString(LEFT, PAGE_HEIGHT - 0.38 * inch, "CLINICAL DOCUMENTATION COPILOT")
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MID)
        c.drawRightString(PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 0.38 * inch, self.section.upper())
        c.line(LEFT, 0.48 * inch, PAGE_WIDTH - RIGHT, 0.48 * inch)
        c.setFont("Helvetica", 6.4)
        c.drawString(LEFT, 0.34 * inch, f"Manideep | {PUBLICATION_DATE}")
        c.drawCentredString(PAGE_WIDTH / 2, 0.34 * inch, "Research report")
        c.drawRightString(PAGE_WIDTH - RIGHT, 0.34 * inch, f"Page {self.page_number} of {TOTAL_PAGES}")
        c.restoreState()

    def add(self, flowable: Any, gap: float = 0) -> float:
        available = max(self.remaining, 1)
        width, height = flowable.wrapOn(self.canvas, self.width, available)
        if height > available + 0.5:
            raise RuntimeError(
                f"Page {self.page_number} overflow: {height:.1f} points required, "
                f"{available:.1f} points available"
            )
        flowable.drawOn(self.canvas, self.x, self.y - height)
        self.y -= height + gap
        return height

    def paragraph(self, text: str, style: str = "body", gap: float | None = None) -> None:
        default_gaps = {
            "body": 6,
            "body_small": 4,
            "bullet": 3,
            "caption": 5,
            "h1": 6,
            "h2": 4,
        }
        self.add(Paragraph(text, STYLES[style]), default_gaps.get(style, 3) if gap is None else gap)

    def heading(self, title: str, kicker: str | None = None) -> None:
        if kicker:
            self.canvas.setFont("Helvetica-Bold", 6.6)
            self.canvas.setFillColor(MID)
            self.canvas.drawString(self.x, self.y - 1, kicker.upper())
            self.y -= 13
        self.paragraph(safe(title), "h1", gap=3)
        self.canvas.setStrokeColor(ACCENT)
        self.canvas.setLineWidth(1.1)
        self.canvas.line(self.x, self.y, self.x + self.width, self.y)
        self.y -= 10

    def subheading(self, title: str) -> None:
        self.paragraph(safe(title), "h2", gap=1)

    def bullet(self, text: str) -> None:
        self.paragraph(f"- {text}", "bullet")

    def spacer(self, height: float) -> None:
        self.y -= height

    def callout(self, title: str, text: str, warning: bool = False) -> None:
        body = Paragraph(
            f"<b>{safe(title)}</b><br/>{text}",
            STYLES["callout"],
        )
        table = Table([[body]], colWidths=[self.width], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F6F2E8") if warning else PALE_2),
                    ("BOX", (0, 0), (-1, -1), 0.7, WARN if warning else RULE),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, WARN if warning else ACCENT),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        self.add(table, gap=7)

    def table(
        self,
        rows: Sequence[Sequence[Any]],
        widths: Sequence[float],
        *,
        small: bool = False,
        header: bool = True,
        before: float = 7,
        gap: float = 6,
    ) -> None:
        body_style = STYLES["table_small" if small else "table"]
        converted: list[list[Any]] = []
        for row_index, row in enumerate(rows):
            converted_row: list[Any] = []
            for cell in row:
                if isinstance(cell, (Paragraph, Table, Spacer)):
                    converted_row.append(cell)
                else:
                    style = STYLES["table_head"] if header and row_index == 0 else body_style
                    converted_row.append(Paragraph(safe(cell), style))
            converted.append(converted_row)
        table = Table(converted, colWidths=list(widths), hAlign="LEFT", repeatRows=1 if header else 0)
        rules = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ]
        if header:
            rules.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("BACKGROUND", (0, 1), (-1, -1), WHITE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE_2]),
                ]
            )
        self.y -= before
        table.setStyle(TableStyle(rules))
        self.add(table, gap=max(gap, 8))

    def keep(self, flowables: Sequence[Any], max_height: float | None = None, gap: float = 0) -> None:
        height = min(max_height if max_height is not None else self.remaining, self.remaining)
        frame = KeepInFrame(self.width, height, list(flowables), mode="shrink", mergeSpace=True)
        self.add(frame, gap=gap)

    def reserve_figure(self, height: float, draw: Callable[[Canvas, float, float, float, float], None]) -> None:
        before = 4
        if height + before > self.remaining:
            raise RuntimeError(f"Page {self.page_number} figure overflow")
        self.y -= before
        bottom = self.y - height
        draw(self.canvas, self.x, bottom, self.width, height)
        self.y = bottom - 8


def metric_cards(page: PageLayout, cards: Sequence[tuple[str, str]]) -> None:
    width = page.width / len(cards)
    rows = [[Paragraph(value, STYLES["metric"]) for value, _ in cards],
            [Paragraph(label, STYLES["metric_label"]) for _, label in cards]]
    table = Table(rows, colWidths=[width] * len(cards), rowHeights=[25, 26])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
                ("BACKGROUND", (0, 0), (-1, -1), PALE_2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    page.add(table, gap=9)


def architecture_figure(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    canvas.saveState()
    canvas.setLineWidth(0.75)

    def tier_box(box_x: float, box_y: float, box_w: float, box_h: float, title: str, detail: str, fill: colors.Color) -> None:
        canvas.setFillColor(fill)
        canvas.setStrokeColor(ACCENT)
        canvas.roundRect(box_x, box_y, box_w, box_h, 4, fill=1, stroke=1)
        title_p = Paragraph(safe(title), ParagraphStyle("ArchTitle", parent=STYLES["table"], fontName="Helvetica-Bold", alignment=TA_CENTER, fontSize=7.6, leading=9))
        detail_p = Paragraph(safe(detail), ParagraphStyle("ArchDetail", parent=STYLES["table_small"], alignment=TA_CENTER, fontSize=6.2, leading=7.4, textColor=MID))
        _, title_h = title_p.wrap(box_w - 12, 20)
        _, detail_h = detail_p.wrap(box_w - 12, box_h - title_h - 10)
        total_h = title_h + 3 + detail_h
        start_y = box_y + (box_h + total_h) / 2 - title_h
        title_p.drawOn(canvas, box_x + 6, start_y)
        detail_p.drawOn(canvas, box_x + 6, start_y - detail_h - 3)

    label_w = 62
    content_x = x + label_w
    content_w = width - label_w
    tier_gap = 12
    tier_h = 46
    band_h = 38
    tier_ys = [
        y + height - tier_h,
        y + height - 2 * tier_h - tier_gap,
        y + height - 3 * tier_h - 2 * tier_gap,
    ]
    tier_labels = ["Experience", "Control plane", "Services"]
    for label, tier_y in zip(tier_labels, tier_ys):
        canvas.setFillColor(MID)
        canvas.setFont("Helvetica-Bold", 6.4)
        canvas.drawRightString(content_x - 9, tier_y + tier_h / 2 - 2, label.upper())

    top_gap = 10
    top_w = (content_w - top_gap) / 2
    tier_box(content_x, tier_ys[0], top_w, tier_h, "Clinician workspace", "Client context, facts, live voice, review, approval", PALE_2)
    tier_box(content_x + top_w + top_gap, tier_ys[0], top_w, tier_h, "EHR and care-plan context", "Patient identity, appointments, CarePlan provenance", PALE_2)

    control_gap = 8
    control_w = (content_w - 2 * control_gap) / 3
    control_items = [
        ("Identity and RBAC", "Trusted gateway, role, session"),
        ("Plan and workflow policy", "Newest active plan, state locks"),
        ("Grounding and validation", "Source binding, sections, review"),
    ]
    for index, (title, detail) in enumerate(control_items):
        tier_box(content_x + index * (control_w + control_gap), tier_ys[1], control_w, tier_h, title, detail, PALE)

    service_gap = 7
    service_w = (content_w - 3 * service_gap) / 4
    service_items = [
        ("FHIR adapter", "Idempotent sync"),
        ("Browser speech", "Permission and transcript"),
        ("Drafting adapters", "Template plus Ollama"),
        ("Repository and audit", "Encrypted fields, revisions"),
    ]
    for index, (title, detail) in enumerate(service_items):
        tier_box(content_x + index * (service_w + service_gap), tier_ys[2], service_w, tier_h, title, detail, WHITE)

    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.7)
    for upper_y, lower_y in zip(tier_ys, tier_ys[1:]):
        arrow_x = content_x + content_w / 2
        start_y = upper_y
        end_y = lower_y + tier_h
        canvas.line(arrow_x, start_y, arrow_x, end_y)
        canvas.line(arrow_x - 3, end_y + 4, arrow_x, end_y)
        canvas.line(arrow_x + 3, end_y + 4, arrow_x, end_y)

    band_y = y
    canvas.setFillColor(ACCENT)
    canvas.setStrokeColor(ACCENT)
    canvas.roundRect(x, band_y, width, band_h, 4, fill=1, stroke=1)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 7.1)
    canvas.drawString(x + 10, band_y + 23, "Cross-cutting assurance")
    canvas.setFont("Helvetica", 6.4)
    canvas.drawString(x + 10, band_y + 10, "Audit linkage | immutable revisions | secret isolation | synthetic evidence | release verification")
    canvas.restoreState()


def workflow_figure(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    canvas.saveState()
    states = ["Scheduled", "In progress", "Documentation pending", "Review required", "Completed"]
    gap = 8
    box_w = (width - gap * 4) / 5
    box_h = 46
    center_y = y + height * 0.60
    for index, state in enumerate(states):
        box_x = x + index * (box_w + gap)
        canvas.setFillColor(PALE_2 if index < 4 else PALE)
        canvas.setStrokeColor(ACCENT)
        canvas.roundRect(box_x, center_y - box_h / 2, box_w, box_h, 3, fill=1, stroke=1)
        p = Paragraph(state, ParagraphStyle("State", parent=STYLES["table"], alignment=TA_CENTER, fontName="Helvetica-Bold"))
        p_w, p_h = p.wrap(box_w - 8, box_h - 6)
        p.drawOn(canvas, box_x + 4, center_y - p_h / 2)
        if index < len(states) - 1:
            start = box_x + box_w
            end = start + gap
            canvas.line(start, center_y, end, center_y)
            canvas.line(end - 3, center_y + 2.5, end, center_y)
            canvas.line(end - 3, center_y - 2.5, end, center_y)

    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.setFillColor(WARN)
    canvas.drawString(x, y + 46, "Fail-closed branch")
    canvas.setFont("Helvetica", 7.1)
    canvas.setFillColor(INK)
    canvas.drawString(
        x + 80,
        y + 46,
        "No active plan: facts may remain pending; voice and generation are denied.",
    )
    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.setFillColor(ACCENT)
    canvas.drawString(x, y + 26, "Terminal branch")
    canvas.setFont("Helvetica", 7.1)
    canvas.setFillColor(INK)
    canvas.drawString(x + 80, y + 26, "Cancelled and completed appointments are locked against mutation.")
    canvas.restoreState()


def grounding_figure(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    canvas.saveState()
    labels = [
        "Allowed source facts",
        "Constrained structuring",
        "Section and plan validation",
        "Clinician review and approval",
    ]
    gap = 13
    box_w = (width - 3 * gap) / 4
    box_h = 58
    box_y = y + 45
    for index, label in enumerate(labels):
        box_x = x + index * (box_w + gap)
        canvas.setFillColor(PALE_2)
        canvas.setStrokeColor(ACCENT)
        canvas.roundRect(box_x, box_y, box_w, box_h, 3, fill=1, stroke=1)
        p = Paragraph(label, ParagraphStyle("Ground", parent=STYLES["table"], alignment=TA_CENTER, fontName="Helvetica-Bold"))
        _, p_h = p.wrap(box_w - 8, box_h - 8)
        p.drawOn(canvas, box_x + 4, box_y + (box_h - p_h) / 2)
        if index < len(labels) - 1:
            start = box_x + box_w
            end = start + gap
            canvas.line(start, box_y + box_h / 2, end, box_y + box_h / 2)
            canvas.line(end - 3, box_y + box_h / 2 + 2.5, end, box_y + box_h / 2)
            canvas.line(end - 3, box_y + box_h / 2 - 2.5, end, box_y + box_h / 2)
    canvas.setFillColor(MID)
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.drawString(x, y + 22, "Denied: unsupported diagnoses, quotations, symptoms, progress, interventions, risk findings, and outcomes.")
    canvas.restoreState()


def dataset_bar_figure(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    rows: Sequence[dict[str, Any]],
) -> None:
    canvas.saveState()
    ranked = sorted(rows, key=lambda row: int(row.get("rows", 0) or 0), reverse=True)[:8]
    if not ranked:
        canvas.setFillColor(MID)
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.drawString(x, y + height / 2, "No relation-level row evidence was available.")
        canvas.restoreState()
        return
    maximum = max(int(row.get("rows", 0) or 0) for row in ranked) or 1
    label_w = 95
    value_w = 60
    bar_w = width - label_w - value_w - 8
    row_h = height / len(ranked)
    for index, row in enumerate(ranked):
        value = int(row.get("rows", 0) or 0)
        bar_len = max(1, bar_w * value / maximum)
        center = y + height - (index + 0.5) * row_h
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawRightString(x + label_w - 6, center - 2.5, str(row.get("file", "relation")))
        canvas.setFillColor(PALE)
        canvas.rect(x + label_w, center - 4, bar_w, 8, fill=1, stroke=0)
        canvas.setFillColor(ACCENT)
        canvas.rect(x + label_w, center - 4, bar_len, 8, fill=1, stroke=0)
        canvas.setFillColor(INK)
        canvas.drawRightString(x + width, center - 2.5, f"{value:,}")
    canvas.restoreState()


def draw_contained_image(
    canvas: Canvas,
    path: Path,
    x: float,
    y: float,
    width: float,
    height: float,
) -> bool:
    if not path.exists():
        canvas.setFillColor(PALE_2)
        canvas.setStrokeColor(RULE)
        canvas.rect(x, y, width, height, fill=1, stroke=1)
        canvas.setFillColor(MID)
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawCentredString(x + width / 2, y + height / 2, "Screenshot evidence unavailable")
        return False
    image = ImageReader(str(path))
    source_w, source_h = image.getSize()
    scale = min(width / source_w, height / source_h)
    draw_w = source_w * scale
    draw_h = source_h * scale
    draw_x = x + (width - draw_w) / 2
    draw_y = y + (height - draw_h) / 2
    canvas.setFillColor(WHITE)
    canvas.setStrokeColor(RULE)
    canvas.roundRect(draw_x - 1.5, draw_y - 1.5, draw_w + 3, draw_h + 3, 4, fill=1, stroke=1)
    canvas.drawImage(image, draw_x, draw_y, draw_w, draw_h, preserveAspectRatio=True, mask="auto")
    return True


def annotated_screenshot_figure(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    path: Path,
    annotations: Sequence[tuple[str, str]],
    image_ratio: float = 0.54,
) -> None:
    canvas.saveState()
    image_w = width * image_ratio
    gap = 18
    draw_contained_image(canvas, path, x, y, image_w, height)
    annotation_x = x + image_w + gap
    annotation_w = width - image_w - gap
    item_gap = 7
    item_h = (height - item_gap * (len(annotations) - 1)) / max(len(annotations), 1)
    for index, (title, detail) in enumerate(annotations, start=1):
        item_y = y + height - index * item_h - (index - 1) * item_gap
        canvas.setFillColor(PALE_2 if index % 2 else WHITE)
        canvas.setStrokeColor(RULE)
        canvas.roundRect(annotation_x, item_y, annotation_w, item_h, 3, fill=1, stroke=1)
        canvas.setFillColor(ACCENT)
        canvas.circle(annotation_x + 14, item_y + item_h - 15, 8, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.drawCentredString(annotation_x + 14, item_y + item_h - 17.2, str(index))
        title_p = Paragraph(safe(title), ParagraphStyle("FeatureTitle", parent=STYLES["table"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.5))
        detail_p = Paragraph(safe(detail), ParagraphStyle("FeatureDetail", parent=STYLES["table_small"], fontSize=6.5, leading=7.8, textColor=MID))
        title_p.wrapOn(canvas, annotation_w - 38, 20)
        title_p.drawOn(canvas, annotation_x + 28, item_y + item_h - 19)
        _, detail_h = detail_p.wrap(annotation_w - 20, item_h - 28)
        detail_p.drawOn(canvas, annotation_x + 10, item_y + 8 + max(0, (item_h - 31 - detail_h) / 2))
    canvas.restoreState()


def client_controls_figure(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    create_path: Path,
    profile_path: Path,
) -> None:
    """Present dissimilar portrait and landscape captures without oversized frames."""
    canvas.saveState()
    gap = 18
    left_w = width * 0.57
    right_w = width - left_w - gap
    label_h = 23
    image_h = height - label_h
    draw_contained_image(canvas, create_path, x, y + label_h, left_w, image_h)

    profile_h = min(image_h * 0.55, right_w * 0.72)
    profile_y = y + height - profile_h
    draw_contained_image(canvas, profile_path, x + left_w + gap, profile_y, right_w, profile_h)

    notes = [
        ("Read-only profile", "Identity, source, plan status, goal, and objective remain visible."),
        ("Browser-local record", "New fictional clients stay in this browser until site data is cleared."),
        ("Required plan context", "Goal, objective, plan dates, and record ID are validated before creation."),
    ]
    note_x = x + left_w + gap
    note_y = y + label_h
    available = profile_y - note_y - 12
    card_gap = 7
    card_h = (available - card_gap * 2) / 3
    for index, (title, detail) in enumerate(notes, start=1):
        card_y = note_y + available - index * card_h - (index - 1) * card_gap
        canvas.setFillColor(PALE_2)
        canvas.setStrokeColor(RULE)
        canvas.roundRect(note_x, card_y, right_w, card_h, 3, fill=1, stroke=1)
        canvas.setFillColor(ACCENT)
        canvas.setFont("Helvetica-Bold", 6.8)
        canvas.drawString(note_x + 9, card_y + card_h - 14, title)
        detail_p = Paragraph(safe(detail), ParagraphStyle("ClientControlDetail", parent=STYLES["table_small"], fontSize=6.2, leading=7.4, textColor=MID))
        _, detail_h = detail_p.wrap(right_w - 18, card_h - 23)
        detail_p.drawOn(canvas, note_x + 9, card_y + 8 + max(0, (card_h - 23 - detail_h) / 2))

    canvas.setFillColor(ACCENT)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawCentredString(x + left_w / 2, y + 7, "Create a fictional browser-local record")
    canvas.drawCentredString(note_x + right_w / 2, y + 7, "Review client and current plan")
    canvas.restoreState()


def two_screenshot_figure(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    left_path: Path,
    right_path: Path,
    left_label: str,
    right_label: str,
) -> None:
    canvas.saveState()
    gap = 14
    panel_w = (width - gap) / 2
    label_h = 23
    draw_contained_image(canvas, left_path, x, y + label_h, panel_w, height - label_h)
    draw_contained_image(canvas, right_path, x + panel_w + gap, y + label_h, panel_w, height - label_h)
    canvas.setFillColor(ACCENT)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawCentredString(x + panel_w / 2, y + 7, left_label)
    canvas.drawCentredString(x + panel_w + gap + panel_w / 2, y + 7, right_label)
    canvas.restoreState()


def performance_figure(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    metrics: dict[str, Any],
) -> None:
    canvas.saveState()
    rows = [
        ("Health", metrics.get("health", {})),
        ("Encrypted client list", metrics.get("client_list_encrypted_fields", {})),
        ("Deterministic generation", metrics.get("deterministic_note_generation", {})),
    ]
    maximum = max(
        [float(values.get("max_ms", 0) or 0) for _, values in rows] + [1.0]
    )
    label_w = 118
    plot_w = width - label_w - 50
    row_h = height / len(rows)
    colors_by_metric = [("p50_ms", HexColor("#7898A8")), ("p95_ms", HexColor("#2F6C7B")), ("max_ms", ACCENT)]
    for row_index, (label, values) in enumerate(rows):
        center_y = y + height - (row_index + 0.5) * row_h
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 6.8)
        canvas.drawRightString(x + label_w - 8, center_y + 5, label)
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(MID)
        canvas.drawRightString(x + label_w - 8, center_y - 7, f"n={fmt_int(values.get('requests'))}")
        for metric_index, (key, fill) in enumerate(colors_by_metric):
            value = float(values.get(key, 0) or 0)
            bar_y = center_y + 10 - metric_index * 10
            canvas.setFillColor(PALE)
            canvas.rect(x + label_w, bar_y, plot_w, 6, fill=1, stroke=0)
            canvas.setFillColor(fill)
            canvas.rect(x + label_w, bar_y, max(1, plot_w * value / maximum), 6, fill=1, stroke=0)
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica", 5.8)
            canvas.drawRightString(x + width, bar_y, f"{key.replace('_ms', '').upper()} {value:.3f} ms")
    canvas.restoreState()


def live_deployment_figure(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    canvas.saveState()

    def box(box_x: float, box_y: float, box_w: float, box_h: float, title: str, detail: str, fill: colors.Color) -> None:
        canvas.setFillColor(fill)
        canvas.setStrokeColor(ACCENT)
        canvas.roundRect(box_x, box_y, box_w, box_h, 4, fill=1, stroke=1)
        title_p = Paragraph(safe(title), ParagraphStyle("DeployTitle", parent=STYLES["table"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.6, alignment=TA_CENTER))
        detail_p = Paragraph(safe(detail), ParagraphStyle("DeployDetail", parent=STYLES["table_small"], fontSize=6.1, leading=7.2, alignment=TA_CENTER, textColor=MID))
        _, title_h = title_p.wrap(box_w - 12, 18)
        _, detail_h = detail_p.wrap(box_w - 12, box_h - title_h - 9)
        total_h = title_h + detail_h + 2
        title_y = box_y + (box_h + total_h) / 2 - title_h
        title_p.drawOn(canvas, box_x + 6, title_y)
        detail_p.drawOn(canvas, box_x + 6, title_y - detail_h - 2)

    top_w = width * 0.36
    top_h = 48
    browser_x = x + (width - top_w) / 2
    browser_y = y + height - top_h
    box(browser_x, browser_y, top_w, top_h, "Public React workspace", "HTTPS, explicit microphone permission, editable review", PALE_2)

    middle_y = y + height * 0.44
    middle_h = 50
    middle_gap = 14
    middle_w = (width - middle_gap) / 2
    box(x, middle_y, middle_w, middle_h, "Browser-local services", "SpeechRecognition, transcript state, fictional client localStorage", WHITE)
    box(x + middle_w + middle_gap, middle_y, middle_w, middle_h, "Vercel serverless gateway", "Same-origin POST, bounded payload, rate limit, no-store response", PALE)

    bottom_y = y
    bottom_h = 48
    bottom_gap = 10
    bottom_w = (width - 2 * bottom_gap) / 3
    box(x, bottom_y, bottom_w, bottom_h, "Browser speech provider", "Vendor-dependent processing; no ClarityNote audio store", WHITE)
    box(x + bottom_w + bottom_gap, bottom_y, bottom_w, bottom_h, "Deterministic fallback", "Grounded template remains available when cloud fails", WHITE)
    box(x + 2 * (bottom_w + bottom_gap), bottom_y, bottom_w, bottom_h, "Ollama gpt-oss:20b", "Low-usage text drafting; key remains in Vercel environment", WHITE)

    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.7)

    def arrow(start_x: float, start_y: float, end_x: float, end_y: float) -> None:
        canvas.line(start_x, start_y, end_x, end_y)
        direction = 1 if end_y >= start_y else -1
        canvas.line(end_x - 3, end_y - 4 * direction, end_x, end_y)
        canvas.line(end_x + 3, end_y - 4 * direction, end_x, end_y)

    arrow(browser_x + top_w / 2, browser_y, x + middle_w / 2, middle_y + middle_h)
    arrow(browser_x + top_w / 2, browser_y, x + middle_w + middle_gap + middle_w / 2, middle_y + middle_h)
    arrow(x + middle_w / 2, middle_y, x + bottom_w / 2, bottom_y + bottom_h)
    arrow(x + middle_w + middle_gap + middle_w / 2, middle_y, x + bottom_w + bottom_gap + bottom_w / 2, bottom_y + bottom_h)
    arrow(x + middle_w + middle_gap + middle_w / 2, middle_y, x + 2 * (bottom_w + bottom_gap) + bottom_w / 2, bottom_y + bottom_h)
    canvas.restoreState()


def report_pages(evidence: EvidenceBundle) -> list[tuple[str, Callable[[PageLayout], None]]]:
    counts = evidence.row_counts
    integrity = evidence.integrity
    receipt = evidence.source_receipt
    files = evidence.row_count_rows
    total_rows = counts.get("all_csv_rows", counts.get("total_rows"))
    clinical_rows = counts.get("clinical_fact_rows")
    patient_count = counts.get("patient_count", integrity.get("patient_count"))
    encounter_count = integrity.get("encounter_count")
    threshold = counts.get("minimum_required_clinical_fact_rows", 1_000_000)
    try:
        threshold_ratio = float(clinical_rows) / float(threshold)
        threshold_ratio_text = f"{threshold_ratio:.2f}x"
    except (TypeError, ValueError, ZeroDivisionError):
        threshold_ratio_text = "Not available"

    warnings = integrity.get("warnings", {}) if isinstance(integrity.get("warnings"), dict) else {}
    medication_anomaly = warnings.get("medications.csv:stop_before_start")
    sources = evidence.references.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    performance = evidence.catalog.get("evidence/tests/performance_results.json", {})
    if not isinstance(performance, dict):
        performance = {}
    performance_metrics = performance.get("metrics", {})
    if not isinstance(performance_metrics, dict):
        performance_metrics = {}
    test_summary = evidence.test_inventory_metadata.get("summary", {})
    if not isinstance(test_summary, dict):
        test_summary = {}
    screenshots = evidence.project_root / "evidence" / "screenshots"

    note_types = [
        ("Case Management Note", "Service Context; Treatment Plan Alignment; Services and Coordination; Client Response; Next Steps", "Coordination and access; supplied services and response only."),
        ("Initial Child Assessment", "Assessment Context; Presenting Information; Developmental and Family Context; Strengths and Needs; Plan", "Developmentally appropriate and neutral; no inferred history."),
        ("Child Assessment Update", "Update Context; Current Information; Changes Since Prior Assessment; Treatment Plan Alignment; Recommendations", "Changes and progress require explicit source support."),
        ("Initial Adult Assessment", "Assessment Context; Presenting Information; Relevant History; Strengths and Needs; Initial Plan", "Separates supplied history from missing information."),
        ("Adult Assessment Update", "Update Context; Current Information; Reported Changes; Treatment Plan Alignment; Plan", "No unsupported comparison or clinical conclusion."),
        ("Counselor Note", "Session Context; Goals and Objectives Addressed; Interventions; Client Response; Plan", "Interventions and response require explicit support."),
        ("Evaluation and Management (E&M) Note", "Encounter Context; History Supplied; Examination and Data; Assessment; Plan", "Never infers examination, diagnosis, code, or medical decision making."),
        ("Nursing Progress Note", "Encounter Context; Subjective Information; Objective Information; Nursing Actions and Response; Plan", "Vitals, medication, assessment, and response must be supplied."),
    ]

    def page_1(page: PageLayout) -> None:
        page.spacer(36)
        page.paragraph(REPORT_TITLE, "title")
        page.paragraph(REPORT_SUBTITLE, "subtitle")
        page.spacer(8)
        page.canvas.setStrokeColor(ACCENT)
        page.canvas.setLineWidth(1.6)
        page.canvas.line(page.x, page.y, page.x + page.width * 0.66, page.y)
        page.spacer(24)
        page.paragraph("<b>Author</b><br/>Manideep", "body")
        page.paragraph(f"<b>Publication date</b><br/>{PUBLICATION_DATE}", "body")
        page.paragraph(f"<b>Evidence snapshot</b><br/>{EVIDENCE_REFRESH_DATE}", "body")
        page.paragraph("<b>Document type</b><br/>Research and engineering report", "body")
        page.spacer(24)
        page.callout(
            "Purpose",
            "This report specifies and evaluates a clinician-controlled reference workflow for grounded clinical note drafting. It combines reproducible synthetic-data evidence, explicit safety boundaries, interoperability mappings, and release-oriented verification requirements.",
        )
        page.spacer(28)
        page.paragraph(
            "The repository is a reference implementation and research artifact. It is not a medical device, does not provide medical advice, and does not establish clinical efficacy or regulatory compliance.",
            "body_small",
        )

    def page_2(page: PageLayout) -> None:
        page.heading("Abstract and key findings", "Executive summary")
        page.paragraph(
            "Clinical documentation systems must reduce clerical work without weakening clinical accountability. This project implements a narrow drafting workflow in which appointment facts and the newest active treatment plan are the permitted clinical sources. The FastAPI reference service uses deterministic structuring; the hosted demonstration can call a protected low-usage Ollama model through a serverless gateway and falls back to the deterministic path. Every draft remains editable and requires clinician review and approval."
        )
        metric_cards(
            page,
            [
                (fmt_int(clinical_rows), "Clinical-fact rows"),
                (fmt_int(total_rows), "All profiled CSV rows"),
                (fmt_int(patient_count), "Synthetic patients"),
                ("8", "Note-type contracts"),
            ],
        )
        page.subheading("Principal findings")
        page.bullet(f"The benchmark records {fmt_int(clinical_rows)} clinical-fact rows, {threshold_ratio_text} the stated {fmt_int(threshold)}-row minimum.")
        page.bullet(f"The integrity scan checked {fmt_int(integrity.get('checked_rows'))} rows and preserved {fmt_int(medication_anomaly)} medication stop-before-start anomalies as warnings.")
        page.bullet("The workflow fails closed when no current active treatment plan is available: voice is denied and generation is deferred.")
        page.bullet("Selected protected fields are encrypted before SQLite persistence; the demonstration defaults are not production key management or full database encryption.")
        page.bullet("FHIR R4 and SMART App Launch are integration targets. Direct clinical-document write-back is not claimed by the reference implementation.")
        page.bullet("The public interface supports browser microphone transcription and browser-local fictional clients; it does not persist audio or shared appointment records.")
        page.callout(
            "Evidence boundary",
            "Synthetic benchmark scale and code-level safeguards support reproducibility and engineering evaluation. They do not demonstrate real-world clinical adequacy, fairness, privacy compliance, or deployment security.",
            warning=True,
        )

    def page_3(page: PageLayout) -> None:
        page.heading("Problem statement and scope", "1. Introduction")
        page.paragraph(
            "A documentation copilot operates at a consequential boundary: it transforms encounter evidence into text that may influence care continuity, billing, and legal records. The central design question is therefore not merely whether text can be produced, but whether the provenance, state, and human accountability of every draft remain visible and enforceable."
        )
        page.subheading("Research questions")
        page.table(
            [
                ["Question", "Operational interpretation"],
                ["RQ1", "Can note drafting be constrained to clinician-supplied facts and the newest active treatment plan?"],
                ["RQ2", "Can voice and generation policy be enforced below the user interface so bypass attempts fail closed?"],
                ["RQ3", "Can a public synthetic benchmark exceed one million clinical facts with traceable provenance and integrity checks?"],
                ["RQ4", "Can the application expose review, approval, revision, locking, and audit boundaries without claiming clinical validation?"],
            ],
            [0.7 * inch, 5.5 * inch],
        )
        page.subheading("In scope")
        page.bullet("FastAPI reference API, encrypted field storage, role permissions, appointment state transitions, and deterministic note structuring.")
        page.bullet("FHIR/SMART read-side mappings, an explicit future write-back boundary, synthetic benchmark profiling, and evidence artifacts.")
        page.bullet("Eight distinct note-type schemas, text and transcript-derived fact workflows, review gates, and immutable completion behavior.")
        page.subheading("Out of scope")
        page.bullet("Autonomous diagnosis, treatment recommendation, coding, billing determination, or unsupervised EHR submission.")
        page.bullet("Claims of HIPAA compliance, clinical effectiveness, population representativeness, or production readiness.")
        page.bullet("Distribution of MIMIC-IV or other credentialed data; restricted datasets are excluded from this public repository.")

    def page_4(page: PageLayout) -> None:
        page.heading("Method and evidence model", "2. Research method")
        page.paragraph(
            "The evaluation uses artifact-centered evidence: repository code defines policy behavior, structured JSON and CSV files record benchmark measurements, and a primary-source register supports standards and governance decisions. Reported counts are loaded directly from the evidence directory when this PDF is generated."
        )
        page.table(
            [
                ["Evidence class", "Loaded artifact", "Interpretation rule"],
                ["Dataset scale", "evidence/dataset/row_counts.json and .csv", "Headers excluded; distinguish clinical-fact rows from all relation rows."],
                ["Integrity", "evidence/dataset/integrity_report.json", "Report passed checks and warnings; do not silently repair source anomalies."],
                ["Provenance", "evidence/dataset/source_receipt.json", "Record source URL, archive checksum, extraction location, and synthetic-data status."],
                ["Automated tests", "evidence/tests/test_inventory.json", "Only inventory outcomes are reportable; absence is a pre-release placeholder."],
                ["Research basis", "docs/research/references.json", "Present titles, publishers, source types, URLs, claims, and caveats in human-readable form."],
            ],
            [1.15 * inch, 2.05 * inch, 3.0 * inch],
            small=True,
        )
        page.subheading("Loaded evidence catalog")
        evidence_rows = [["Artifact", "Record summary"]]
        for name, value in sorted(evidence.catalog.items()):
            if isinstance(value, list):
                summary = f"{len(value):,} records"
            elif isinstance(value, dict) and "load_error" in value:
                summary = f"Load error: {value['load_error']}"
            elif isinstance(value, dict):
                summary = f"{len(value):,} top-level fields"
            else:
                summary = type(value).__name__
            evidence_rows.append([name, summary])
        if len(evidence_rows) == 1:
            evidence_rows.append(["No evidence files loaded", "Build is incomplete"])
        page.table(evidence_rows, [4.7 * inch, 1.5 * inch], small=True)
        page.callout(
            "Temporal transparency",
            f"The publication and evidence snapshot are fixed at {PUBLICATION_DATE}. Public artifacts use this reproducible snapshot label instead of embedding the workstation's build date; source review dates are kept before the publication baseline.",
        )

    def page_5(page: PageLayout) -> None:
        page.heading("Reference architecture", "3. System design")
        page.paragraph(
            "The architecture separates the clinician workspace, policy-enforcing application core, controlled adapters, persistence, and evidence collection. The separation allows plan selection, authorization, state transition, and voice controls to be checked at multiple boundaries."
        )
        page.reserve_figure(225, architecture_figure)
        page.paragraph("Figure 1. Logical architecture and cross-cutting control plane.", "caption")
        page.subheading("Deployment interpretation")
        page.bullet("The browser is not trusted to select the authoritative treatment plan or grant itself permissions.")
        page.bullet("The service resolves the newest effective active plan, binds its identifier to generation, and rechecks workflow state before approval and completion.")
        page.bullet("External identity, FHIR, speech, inference, key management, database, backup, and monitoring services are adapter responsibilities in a production deployment.")
        page.callout(
            "Reference boundary",
            "The current stack demonstrates domain controls locally. Organization-approved infrastructure, security operations, clinical governance, and privacy review remain deployment obligations.",
            warning=True,
        )

    def page_6(page: PageLayout) -> None:
        page.heading("Components and safety boundaries", "3. System design")
        page.table(
            [
                ["Component", "Primary responsibility", "Enforced boundary"],
                ["Clinician workspace", "Setup, fact capture, review, edit, approval", "Completion requires approved and validated content."],
                ["API and identity adapter", "Validate gateway assertions, role, session, and inputs", "Deny unauthenticated, expired, or unauthorized operations."],
                ["Workflow service", "Manage status transitions and locks", "Reject invalid transitions and completed-record mutation."],
                ["Plan policy", "Select newest currently effective active plan", "Ignore caller-selected historical plan identifiers."],
                ["Grounded generator", "Structure allowed evidence into the note schema", "Leave unsupported content explicitly missing."],
                ["Voice policy gateway", "Validate plan state and transcript constraints", "Reject voice workflow when active plan is absent."],
                ["Clinical repository", "Store protected fields, revisions, receipts, and audit events", "Encrypt selected fields and chain audit entries."],
                ["FHIR adapter target", "Synchronize identity and care-plan state", "Use idempotency and preserve upstream provenance."],
                ["Evidence pipeline", "Profile synthetic data and collect release evidence", "Keep real and restricted records out of the repository."],
            ],
            [1.2 * inch, 2.45 * inch, 2.55 * inch],
            small=True,
        )
        page.subheading("Trust boundaries")
        page.bullet("Browser to API; application to EHR; services to persistence; voice capture to speech processing; generation adapter to inference runtime; and application events to monitoring.")
        page.bullet("Every boundary requires explicit authentication, authorization, input limits, provenance, and failure behavior appropriate to the deployment.")
        page.callout(
            "Persistence precision",
            "The reference repository applies Fernet authenticated encryption to selected text and JSON values before SQLite storage. SQLite pages, indexes, metadata, process memory, backups, and runtime secrets require additional deployment controls.",
        )

    def page_7(page: PageLayout) -> None:
        page.heading("Appointment workflow and plan invariant", "4. Workflow")
        page.reserve_figure(150, workflow_figure)
        page.paragraph("Figure 2. Primary appointment state path and fail-closed branches.", "caption")
        page.subheading("Newest-active-plan invariant")
        page.table(
            [
                ["Step", "Rule"],
                ["1", "Filter to plans whose lifecycle status is ACTIVE."],
                ["2", "Require effective_date on or before the decision date."],
                ["3", "Require no expiration date or an expiration date on or after the decision date."],
                ["4", "Order by effective date, upstream update timestamp, and local identifier, descending."],
                ["5", "Select one newest plan; fail closed if none is eligible or equally current candidates remain."],
            ],
            [0.55 * inch, 5.65 * inch],
        )
        page.subheading("State guarantees")
        page.bullet("Six or seven unique clinician-supplied text facts can be stored while documentation waits for a current plan.")
        page.bullet("Generated drafts retain plan and source-snapshot bindings; any later change requires regeneration before approval or completion.")
        page.bullet("Generated missing-data markers prevent approval until the clinician supplies or explicitly resolves required content.")
        page.bullet("Completed and cancelled appointments are terminal; the service rejects later mutation.")

    def page_8(page: PageLayout) -> None:
        page.heading("FHIR R4 and SMART boundary", "5. Interoperability")
        page.paragraph(
            "The interoperability design distinguishes read synchronization from clinical-document write-back. SMART App Launch with OAuth 2.0 and OpenID Connect is the intended authorization profile, while target-server capabilities and organization-specific profiles must be discovered and tested."
        )
        page.table(
            [
                ["Local concept", "FHIR R4 target", "Mapping and caution"],
                ["Client", "Patient", "Use issuer-qualified identifiers; do not deduplicate by name and birth date alone."],
                ["Staff", "Practitioner / PractitionerRole", "Resolve organization and permitted service role."],
                ["Appointment", "Appointment / Encounter", "Keep planned administrative status distinct from performed clinical interaction."],
                ["Treatment plan", "CarePlan", "Preserve lifecycle, period, goals, activities, version, and provenance."],
                ["Treatment goal", "Goal or CarePlan.goal", "Retain references and lifecycle status."],
                ["Approved document", "Composition / DocumentReference target", "Write only after EHR-specific profile, authorization, and reconciliation testing."],
                ["Audit", "AuditEvent target", "Keep local security audit separate from note narrative."],
            ],
            [1.1 * inch, 1.45 * inch, 3.65 * inch],
            small=True,
        )
        page.subheading("Synchronization semantics")
        page.bullet("Upsert on issuer plus external identifier; record upstream version and lastUpdated for conflict detection.")
        page.bullet("Process pages and retries idempotently; represent inactive or deleted upstream state as lifecycle change, not silent hard deletion.")
        page.bullet("Quarantine ambiguous identifiers and equally current plans for review in a production adapter.")
        page.callout(
            "No write-back claim",
            "The demonstrated export is user-controlled copy of an approved draft. A future direct write adapter must add capability discovery, conditional writes, duplicate prevention, provenance, error recovery, reconciliation, and a visible receipt.",
            warning=True,
        )

    def page_9(page: PageLayout) -> None:
        page.heading("Synthetic benchmark provenance", "6. Data")
        page.paragraph(
            "The benchmark uses the official MITRE Synthea COVID-19 10K CSV archive. Synthea records are synthetic; the repository does not include MIMIC-IV or other credentialed patient data. Raw benchmark files remain outside version control and are reproduced from the recorded source receipt."
        )
        page.table(
            [
                ["Receipt field", "Recorded value"],
                ["Source", receipt.get("source", "Not available")],
                ["Archive", receipt.get("archive", "Not available")],
                ["Archive bytes", fmt_int(receipt.get("archive_bytes"))],
                ["Archive SHA-256", receipt.get("archive_sha256", "Not available")],
                ["Evidence snapshot (UTC)", receipt.get("evidence_snapshot_at_utc", receipt.get("downloaded_at_utc", "Not available"))],
                ["Extracted files", fmt_int(receipt.get("extracted_file_count"))],
                ["Synthetic data only", safe(receipt.get("synthetic_data_only"))],
                ["Restricted data included", safe(receipt.get("restricted_data_included"))],
            ],
            [1.55 * inch, 4.65 * inch],
            small=True,
        )
        page.subheading("Dataset selection rationale")
        page.bullet("A public, reproducible artifact can include scripts and aggregate evidence without redistributing restricted health records.")
        page.bullet("MIMIC-IV is excluded because access is credentialed and governed by a data-use agreement; its absence is a repository design decision, not a judgment about research value.")
        page.bullet("Synthetic status removes patient privacy exposure from the benchmark itself, but it does not validate clinical safety or production security.")
        page.callout(
            "Terminology caveat",
            "Synthea software is Apache-2.0 licensed, while embedded terminology content can have separate conditions. The repository NOTICE and the exact upstream revision must be reviewed for redistribution.",
        )

    def page_10(page: PageLayout) -> None:
        page.heading("Dataset scale and relation profile", "6. Data")
        metric_cards(
            page,
            [
                (fmt_int(clinical_rows), "Clinical-fact rows"),
                (fmt_int(total_rows), "All CSV rows"),
                (fmt_int(counts.get("file_count")), "Profiled relations"),
                (fmt_int(patient_count), "Synthetic patients"),
            ],
        )
        page.reserve_figure(215, lambda c, x, y, w, h: dataset_bar_figure(c, x, y, w, h, files))
        page.paragraph("Figure 3. Eight largest profiled relations by header-excluded data rows.", "caption")
        largest = sorted(files, key=lambda row: int(row.get("rows", 0) or 0), reverse=True)[:5]
        table_rows = [["Relation", "Rows", "Columns", "Bytes"]]
        for row in largest:
            table_rows.append(
                [
                    row.get("file", "Not available"),
                    fmt_int(row.get("rows")),
                    fmt_int(row.get("columns")),
                    fmt_int(row.get("bytes")),
                ]
            )
        page.table(table_rows, [2.45 * inch, 1.15 * inch, 1.05 * inch, 1.55 * inch], small=True)
        page.callout(
            "Counting definition",
            safe(counts.get("definition", "Sum of data rows across profiled relation files; headers excluded.")),
        )

    def page_11(page: PageLayout) -> None:
        page.heading("Integrity results and preserved anomaly", "6. Data")
        page.paragraph(
            "The integrity evidence reports successful referential, temporal, and core-identifier checks with a warning for a source anomaly. The anomaly is retained in the benchmark so downstream quarantine behavior can be evaluated instead of hidden by silent correction."
        )
        page.table(
            [
                ["Check", "Observed result"],
                ["Overall status", integrity.get("status", "Not available")],
                ["Rows checked", fmt_int(integrity.get("checked_rows"))],
                ["Patient foreign keys checked", fmt_int(integrity.get("patient_foreign_keys_checked"))],
                ["Encounter foreign keys checked", fmt_int(integrity.get("encounter_foreign_keys_checked"))],
                ["Temporal ranges checked", fmt_int(integrity.get("temporal_ranges_checked"))],
                ["Duplicate patient IDs", fmt_int((integrity.get("uniqueness") or {}).get("patients_duplicate_ids"))],
                ["Duplicate encounter IDs", fmt_int((integrity.get("uniqueness") or {}).get("encounters_duplicate_ids"))],
                ["Recorded violations", compact_json(integrity.get("violations", {}))],
            ],
            [2.55 * inch, 3.65 * inch],
        )
        page.callout(
            "Observed source anomaly",
            f"The scan recorded {fmt_int(medication_anomaly)} rows in medications.csv where STOP precedes START. The evidence policy is: {safe(integrity.get('warning_policy', 'Preserve, report, and quarantine source anomalies for review.'))}",
            warning=True,
        )
        page.subheading("Operational treatment")
        page.bullet("Do not rewrite the upstream benchmark while profiling; preserve checksums and original values.")
        page.bullet("Quarantine anomalous records before operational ingestion and attach a machine-readable reason.")
        page.bullet("Measure the effect of exclusion or correction separately and retain the decision trail.")
        page.bullet("Do not interpret passed structural checks as evidence of clinical truth or population validity.")

    def page_12(page: PageLayout) -> None:
        page.heading("Grounded drafting safeguards", "7. AI safety")
        page.paragraph(
            "The FastAPI reference generator is deterministic: it receives an intentionally small evidence packet and adds labels, note sections, and explicit missing-data markers. The hosted interface can use gpt-oss:20b behind a fixed server prompt, bounded inputs, same-origin checks, rate controls, output validation, and the same clinician review gate. If cloud drafting is unavailable, the deterministic template remains the safety fallback."
        )
        page.reserve_figure(150, grounding_figure)
        page.paragraph("Figure 4. Grounding, validation, and human-approval sequence.", "caption")
        page.table(
            [
                ["Allowed input", "Permitted use", "Denied behavior"],
                ["Appointment metadata", "Document control and encounter context", "No inference from staff name, service type, or date."],
                ["Newest active plan", "Goals, objectives, and plan identifier", "No historical or caller-selected plan substitution."],
                ["Six or seven text facts", "Verbatim factual grounding", "No instruction execution or added clinical claims."],
                ["Diarized transcript turns", "Supplied speaker-attributed facts", "No invented quotation or speaker attribution."],
                ["Missing markers", "Require clinician completion", "No fluent guess to conceal absent evidence."],
            ],
            [1.45 * inch, 2.25 * inch, 2.5 * inch],
            small=True,
        )
        page.subheading("Human control")
        page.bullet("The draft is visibly a review artifact; generation does not equal approval or completion.")
        page.bullet("Editing creates a new revision and clears prior review state; a clinician must review again.")
        page.bullet("Completion locks the appointment, while later changes require a governed amendment workflow outside this reference scope.")

    def page_13(page: PageLayout) -> None:
        page.heading("Voice workflow and data-minimization controls", "7. AI safety")
        page.paragraph(
            "Voice is treated as a higher-risk optional path. The hosted interface requests microphone access only after a user action and uses browser-native speech recognition for interim and final text. ClarityNote retains only the editable transcript in page state; browser vendors may provide the underlying speech service. The reference API separately accepts supplied diarized transcript text and duration metadata and has no raw-audio upload route."
        )
        page.table(
            [
                ["Decision point", "Reference behavior", "Production obligation"],
                ["Plan state", "Voice allowed only when a current active plan is resolved server-side.", "Recheck on every capture, upload, process, retry, and retention operation."],
                ["Hosted capture", "Require six complete factual statements before mapping transcript text into review fields.", "Validate transcription accuracy, consent, browser support, and organization policy."],
                ["Maximum duration", "Schema caps duration at 14,400 seconds.", "Add byte, codec, channel, and rate limits before receiving content."],
                ["Speaker coverage", "Require both STAFF and CLIENT transcript turns.", "Validate diarization quality and provide correction tools."],
                ["Raw audio", "No raw-audio persistence path; the public client does not upload recordings.", "Review browser speech-provider behavior and use an approved service for sensitive deployments."],
                ["Generation", "Transcript text is untrusted clinical data, never executable instructions.", "Apply content isolation, provenance, monitoring, and clinician review."],
            ],
            [1.25 * inch, 2.45 * inch, 2.5 * inch],
            small=True,
        )
        page.callout(
            "Expired-plan invariant",
            "When the current plan is absent or expired, the system must disable voice in the interface and reject the API request before accepting audio bytes or retaining transcript content.",
            warning=True,
        )
        page.subheading("Residual voice risks")
        page.bullet("Consent ambiguity, bystander capture, diarization error, transcription error, local-device compromise, and temporary-file persistence remain deployment concerns.")
        page.bullet("Human review must compare the draft to the encounter evidence; speaker labels are not proof that a quotation is correct.")

    def note_page(page: PageLayout, start: int, title: str) -> None:
        page.heading(title, "8. Documentation contracts")
        page.paragraph(
            "Every note type has a distinct section contract but shares the same grounding rule: use only appointment facts, the newest active plan, and clinician-supplied facts; mark unsupported information for clinician input."
        )
        rows = [["Note type", "Required sections", "Safety-specific style rule"]]
        for name, sections_text, rule in note_types[start : start + 4]:
            rows.append([name, sections_text, rule])
        page.table(rows, [1.5 * inch, 2.75 * inch, 1.95 * inch], small=True)
        page.subheading("Shared required fields")
        page.bullet("Appointment date, service type, selected treatment goals, selected objectives, and supplied session facts.")
        page.subheading("Validation behavior")
        page.bullet("An empty note or a note missing any required section is rejected by template validation.")
        page.bullet("Generated missing-data markers intentionally force a clinician edit before approval.")
        page.bullet("A probabilistic model, if later enabled, must remain behind the same source restriction, section validator, plan linkage, revision, and human-approval gates.")
        page.callout(
            "Template scope",
            "A structurally valid template is not proof that a note is clinically complete, correct, billable, or appropriate for a particular organization.",
            warning=True,
        )

    def page_14(page: PageLayout) -> None:
        note_page(page, 0, "Eight note types: service and assessment")

    def page_15(page: PageLayout) -> None:
        note_page(page, 4, "Eight note types: clinical updates and progress")

    def page_16(page: PageLayout) -> None:
        page.heading("Security and privacy architecture", "9. Security")
        page.paragraph(
            "The reference implementation includes code-level safeguards but does not claim HIPAA compliance. Compliance depends on the deployed organization, risk analysis, policies, contracts, operations, infrastructure, and verified technical controls."
        )
        page.table(
            [
                ["Control area", "Implemented reference behavior", "Additional deployment requirement"],
                ["Identity", "Trusted-gateway token, user ID, role, and session-expiry validation", "Approved OIDC/SMART identity, TLS, secure cookies, lifecycle and reauthentication."],
                ["Authorization", "Central role-permission matrix and protected endpoints", "Least-privilege design, periodic access review, emergency access, and segregation of duties."],
                ["Confidentiality", "Fernet encryption of selected text and JSON fields", "Managed keys, rotation, full storage and backup encryption, memory and endpoint controls."],
                ["Integrity", "Schema constraints, revision records, idempotency receipts, HMAC-chained audit entries", "Append-only protected logging, monitoring, time integrity, retention, and independent verification."],
                ["Data minimization", "No raw note text in intended audit metadata; no raw-audio persistence path", "Logging review, redaction tests, retention schedules, secure deletion, and incident procedures."],
                ["Availability", "Bounded input schemas and database transactions", "Rate limits, capacity tests, backups, recovery objectives, continuity exercises, and failover."],
            ],
            [1.1 * inch, 2.35 * inch, 2.75 * inch],
            small=True,
        )
        page.callout(
            "Development-secret warning",
            "The settings module includes local development defaults so the demonstration can run. Production must supply unique high-entropy secrets through an approved secret manager and must never reuse repository defaults.",
            warning=True,
        )
        page.subheading("Privacy engineering priorities")
        page.bullet("Classify every field, minimize collection, bind purpose and retention, restrict audit access, test deletion, and prohibit PHI in logs, screenshots, fixtures, and error traces.")

    def page_17(page: PageLayout) -> None:
        page.heading("Threat model", "9. Security")
        page.paragraph(
            "The STRIDE analysis considers client identity, plan state, encounter facts, drafts, revisions, transient voice data, credentials, audit evidence, and role assignments across six trust boundaries."
        )
        page.table(
            [
                ["Threat", "Representative case", "Primary controls", "Verification focus"],
                ["Spoofing", "Reuse another clinician session", "Gateway assertion, short session, target OIDC/SMART", "Authentication and expiry denial tests"],
                ["Tampering", "Change plan identifier during generation", "Server-side selection, plan binding, revisions", "Plan-selection and mutation tests"],
                ["Repudiation", "Deny approval or export", "Actor/time/action audit events", "Audit integrity and authorization tests"],
                ["Information disclosure", "Sensitive content in logs or traces", "Content-minimized audit, generic errors, encryption", "Log scanning and error-path tests"],
                ["Denial of service", "Oversized transcript or repeated generation", "Schema bounds, parsing limits, target throttling", "Boundary, load, and recovery tests"],
                ["Elevation of privilege", "Counselor manages templates or syncs EHR", "Central permission matrix, deny by default", "Complete role-operation matrix"],
            ],
            [0.75 * inch, 1.7 * inch, 2.1 * inch, 1.65 * inch],
            small=True,
        )
        page.subheading("High-priority misuse cases")
        page.bullet("UI bypass for expired-plan voice: API must reject before content retention.")
        page.bullet("Historical-plan injection: service must ignore the caller-selected plan and resolve current state.")
        page.bullet("Prompt-like text inside a bullet or transcript: treat it as untrusted data, not an instruction.")
        page.bullet("Copy or complete unreviewed content: keep finalization unavailable until review, validation, and approval.")
        page.bullet("Mutation of a terminal appointment: reject the change and retain prior revisions.")
        page.callout(
            "Residual clinical risk",
            "No automated safeguard establishes clinical correctness. Incomplete facts, contextual mismatch, automation bias, and a model's unsupported output require qualified review, incident feedback, and a reliable disable mechanism.",
            warning=True,
        )

    def page_18(page: PageLayout) -> None:
        page.heading("Verification strategy and release gates", "10. Validation")
        page.paragraph(
            "Each high-risk rule needs both a success case and a denial case at the API or domain layer. User-interface behavior alone is insufficient because a caller can bypass disabled controls. The following matrix defines planned evidence categories; actual automated outcomes appear only when the test inventory artifact is present."
        )
        page.table(
            [
                ["Area", "Required success evidence", "Required denial or boundary evidence"],
                ["Plan policy", "Newest effective active plan selected", "Expired, inactive, missing, and ambiguous states fail closed"],
                ["Grounding", "Supplied facts and selected plan retained", "Missing or malicious input adds no unsupported claim"],
                ["Voice", "Eligible diarized transcript accepted", "Expired plan, too-short duration, invalid speakers, and oversized input rejected"],
                ["State", "Reviewed and approved note completes and locks", "Unapproved completion and terminal mutation rejected"],
                ["RBAC", "Authorized role performs operation", "Every non-permitted role-operation pair denied"],
                ["Sync", "Idempotent replay returns the same result", "Request-ID reuse with changed payload conflicts"],
                ["Data", "Source receipt, hashes, counts, and threshold recorded", "Schema, reference, temporal, uniqueness, and anomaly checks recorded"],
                ["PDF", f"Exactly {TOTAL_PAGES} pages with metadata and extractable text", "Rendered-page review finds no clipping, overlap, or unreadable tables"],
            ],
            [1.0 * inch, 2.55 * inch, 2.65 * inch],
            small=True,
        )
        page.subheading("Release gates")
        page.bullet("Automated tests pass with no unexpected skips; evidence includes tool, timestamp, environment, and failure detail.")
        page.bullet("Frontend builds and API starts; health behavior, security headers, repository secret scan, and tracked-file review are recorded.")
        page.bullet("Raw data, recordings, databases, credentials, and sensitive samples are not tracked.")
        page.bullet("The generated PDF passes page-count, metadata, text-extraction, and rendered visual review.")
        page.bullet("Clinical validation remains a separate pre-deployment activity with qualified reviewers and acceptance criteria.")

    def page_19(page: PageLayout) -> None:
        page.heading("Executed tests and latency profile", "10. Quantitative evidence")
        metric_cards(
            page,
            [
                (fmt_int(test_summary.get("backend_tests")), "Backend tests"),
                (fmt_int(test_summary.get("frontend_tests")), "Frontend tests"),
                (fmt_int(test_summary.get("release_gates")), "Release gates"),
                (fmt_int(test_summary.get("failed_records", []) and len(test_summary.get("failed_records", [])) or 0), "Failed records"),
            ],
        )
        page.paragraph(
            "The latency evidence is an in-process regression benchmark, not a production load test. It isolates three API paths so changes in cryptography, serialization, policy evaluation, or note assembly can be detected before release.",
            "body_small",
        )
        page.reserve_figure(205, lambda c, x, y, w, h: performance_figure(c, x, y, w, h, performance_metrics))
        page.paragraph("Figure 5. Local latency distribution by p50, p95, and observed maximum.", "caption")
        latency_rows = [["Path", "Requests", "p50 ms", "p95 ms", "p99 ms", "Maximum ms"]]
        for label, key in [
            ("Health", "health"),
            ("Encrypted client list", "client_list_encrypted_fields"),
            ("Deterministic generation", "deterministic_note_generation"),
        ]:
            values = performance_metrics.get(key, {})
            latency_rows.append(
                [
                    label,
                    fmt_int(values.get("requests")),
                    safe(values.get("p50_ms")),
                    safe(values.get("p95_ms")),
                    safe(values.get("p99_ms")),
                    safe(values.get("max_ms")),
                ]
            )
        page.table(latency_rows, [1.7 * inch, 0.75 * inch, 0.85 * inch, 0.85 * inch, 0.85 * inch, 1.2 * inch], small=True)
        page.callout(
            "Interpretation boundary",
            safe(performance.get("scope_warning", "Latency values are local regression evidence only.")),
            warning=True,
        )

    def page_20(page: PageLayout) -> None:
        page.heading("Hosted demonstration architecture", "10. Deployment evidence")
        page.paragraph(
            "The public Vercel deployment keeps speech capture, custom fictional records, and review state in the visitor's browser. Text drafting crosses the network only through a same-origin serverless function. The Ollama credential is stored as a sensitive Vercel environment variable and is never bundled into the React application."
        )
        page.reserve_figure(260, live_deployment_figure)
        page.paragraph("Figure 6. Public demonstration data flow and secret boundary.", "caption")
        page.table(
            [
                ["Boundary", "Implemented behavior", "Residual obligation"],
                ["Microphone", "Permission requested only after the user starts transcription; ClarityNote stores no audio.", "Browser speech-provider behavior and consent require deployment review."],
                ["Custom client", "Fictional record stored only in localStorage for that browser.", "No real patient information; clear site data to remove the record."],
                ["AI drafting", "Fixed gpt-oss:20b model, bounded payload, strict prompt, no-store response, deterministic fallback.", "Public quota and instance-local rate limiting are demonstration constraints."],
                ["Review", "Generated text remains editable and cannot be approved until clinician review is checked.", "Production identity, authorization, audit, and write-back remain separate."],
            ],
            [1.05 * inch, 2.7 * inch, 2.45 * inch],
            small=True,
        )

    def page_21(page: PageLayout) -> None:
        page.heading("Interface evidence: appointment workspace", "10. Product walkthrough")
        page.paragraph(
            "The workspace is organized as a single clinical task path. The screenshot is captured from the tested React build and uses fictional client information."
        )
        page.reserve_figure(
            345,
            lambda c, x, y, w, h: draw_contained_image(
                c,
                screenshots / "active-plan-workflow.png",
                x,
                y,
                w,
                h,
            ),
        )
        page.paragraph("Figure 7. Active-plan appointment workspace in the public interface.", "caption")
        page.table(
            [
                ["Region", "Purpose"],
                ["Workflow progress", "Makes the current documentation stage and remaining review work visible."],
                ["Client and plan card", "Keeps identity cues, plan status, goal, objective, and effective dates in view."],
                ["Appointment setup", "Captures service date, clinician, service type, and one of eight note contracts."],
                ["Dual workspace", "Places factual input beside the editable generated note so evidence and output can be compared."],
            ],
            [1.35 * inch, 4.85 * inch],
            small=True,
        )

    def page_22(page: PageLayout) -> None:
        page.heading("Interface evidence: live voice", "10. Product walkthrough")
        page.paragraph(
            "Voice capture is a review-first interaction. Browser support is detected at runtime, a typed or pasted transcript remains available as a fallback, and six complete statements are required before facts are populated."
        )
        page.reserve_figure(
            350,
            lambda c, x, y, w, h: annotated_screenshot_figure(
                c,
                x,
                y,
                w,
                h,
                screenshots / "live-voice-workflow.png",
                [
                    ("Explicit mode", "Voice is a deliberate choice and remains blocked when the treatment plan is expired."),
                    ("Realtime transcript", "Interim phrases and finalized text remain editable before they become source facts."),
                    ("Permission-led controls", "Start and stop actions drive the browser microphone permission and listening state."),
                    ("Privacy boundary", "The interface states that audio is not saved and browser speech policy must be reviewed."),
                    ("Structured handoff", "Transcript text is mapped into seven labeled fields for clinician correction."),
                ],
                image_ratio=0.54,
            ),
        )
        page.paragraph("Figure 8. Live microphone transcription and transcript-to-fact handoff.", "caption")
        page.callout(
            "Compatibility",
            "SpeechRecognition is not available uniformly across browsers. The editable transcript fallback keeps the workflow usable without pretending unsupported browsers can capture live speech.",
        )

    def page_23(page: PageLayout) -> None:
        page.heading("Interface evidence: client controls", "10. Product walkthrough")
        page.paragraph(
            "The public experience supports a complete fictional workflow instead of limiting visitors to two preloaded examples. The creation form is intentionally separated from the read-only profile view."
        )
        page.reserve_figure(
            330,
            lambda c, x, y, w, h: client_controls_figure(
                c,
                x,
                y,
                w,
                h,
                screenshots / "create-test-client.png",
                screenshots / "client-profile-detail.png",
            ),
        )
        page.paragraph("Figure 9. Focused client-creation and profile views.", "caption")
        page.bullet("Required goal, objective, plan, identity, and date fields prevent an unusable record from being created.")
        page.bullet("A prominent warning prohibits real patient information and explains that the record stays in the current browser.")
        page.bullet("The profile view exposes record source, demographics, plan status, goal, and current objective without enabling hidden edits.")

    def page_24(page: PageLayout) -> None:
        page.heading("Interface evidence: review and approval", "10. Product walkthrough")
        page.paragraph(
            "Draft generation is not the terminal action. The note remains editable, identifies the grounding source, and keeps approval and copy unavailable until the clinician confirms a complete review."
        )
        page.reserve_figure(
            420,
            lambda c, x, y, w, h: annotated_screenshot_figure(
                c,
                x,
                y,
                w,
                h,
                screenshots / "generated-note-review.png",
                [
                    ("Grounding receipt", "The interface identifies the plan, fact count, appointment inputs, note type, and drafting path."),
                    ("Editable draft", "Clinicians can correct every section before review or approval is recorded."),
                    ("Safety cue", "The workspace explicitly states that no diagnosis was added automatically."),
                    ("Human gate", "Approval and copy remain disabled until the full-note review checkbox is selected."),
                ],
                image_ratio=0.54,
            ),
        )
        page.paragraph("Figure 10. Generated note review, source receipt, and disabled approval controls.", "caption")
        page.callout(
            "Human accountability",
            "The model or deterministic template can accelerate drafting, but the clinician remains responsible for correcting, approving, and completing the record.",
            warning=True,
        )

    def test_page(page: PageLayout, part: int) -> None:
        page.heading(f"Automated test appendix {part} of 4", "Appendix A")
        if not evidence.tests_present or not evidence.tests:
            reason = (
                "The inventory file was found but contained no readable test records."
                if evidence.tests_present
                else "The inventory file is absent."
            )
            page.callout(
                "PRE-RELEASE PLACEHOLDER - NO TEST RESULTS CLAIMED",
                f"{reason} Expected path: {safe(evidence.test_inventory_path.as_posix())}. This report therefore makes no claim that the automated suite passed, failed, was collected, or was executed.",
                warning=True,
            )
            if part == 1:
                page.subheading("Required inventory content")
                page.bullet("One record for every collected test, including a stable identifier or node ID, descriptive name, layer, and outcome.")
                page.bullet("Execution timestamp, command, environment, dependency versions, duration, skipped-test reasons, and failure diagnostics.")
                page.bullet("A summary whose totals reconcile exactly to the exhaustive record list.")
            elif part == 2:
                page.subheading("Evidence capture protocol")
                page.bullet("Collect the full backend and frontend test inventories without filtering failed or skipped cases.")
                page.bullet("Write the JSON atomically after the run and preserve the command exit code and environment fingerprint.")
                page.bullet("Do not substitute source-code discovery for execution evidence; a test function is not a passing result.")
                page.bullet("Regenerate this report only after the inventory artifact is available and reviewed.")
            else:
                page.subheading("Pre-release interpretation")
                page.bullet("All verification descriptions elsewhere in this report are requirements or code-level design observations, not executed outcomes.")
                page.bullet("A release decision must remain open until failures, skips, browser checks, security scans, and PDF visual QA have evidence.")
                page.bullet("If the test inventory disagrees with any narrative statement, the structured evidence controls and the discrepancy must be resolved.")
            return

        chunks = split_evenly(evidence.tests, 4)
        chunk = chunks[part - 1]
        statuses: dict[str, int] = {}
        for test in evidence.tests:
            key = str(test.get("status", "not recorded")).strip().lower() or "not recorded"
            statuses[key] = statuses.get(key, 0) + 1
        if part == 1:
            page.paragraph(
                f"Inventory evidence contains {len(evidence.tests):,} test records. Status totals: "
                + ", ".join(f"{safe(key)}={value:,}" for key, value in sorted(statuses.items()))
                + ". Totals are descriptive only; release interpretation depends on the recorded status semantics and complete run metadata.",
                "body_small",
            )
            page.paragraph(
                f"Run summary: backend={fmt_int(test_summary.get('backend_tests'))}, frontend={fmt_int(test_summary.get('frontend_tests'))}, release gates={fmt_int(test_summary.get('release_gates'))}, failed checks={fmt_int(len(test_summary.get('failed_checks', [])))}.",
                "caption",
            )
        else:
            page.paragraph(
                f"Continuation of the complete inventory: records {chunk[0]['index'] if chunk else 0} through {chunk[-1]['index'] if chunk else 0}.",
                "body_small",
            )
        test_rows: list[list[Any]] = [["# / ID", "Name and coverage", "Status / recorded metadata"]]
        for test in chunk:
            details = test.get("description", "")
            test_rows.append(
                [
                    f"{test['index']}. {safe(test['id'])}",
                    f"{safe(test['name'])}" + (f"<br/><font color='#5E6871'>{safe(details)}</font>" if details else ""),
                    f"<b>{safe(test['status'])}</b>" + (f"<br/>{safe(test['metadata'])}" if test.get("metadata") else ""),
                ]
            )
        converted = []
        for row_index, row in enumerate(test_rows):
            converted.append(
                [
                    Paragraph(str(cell), STYLES["table_head"] if row_index == 0 else STYLES["test"])
                    for cell in row
                ]
            )
        table = Table(converted, colWidths=[1.25 * inch, 2.95 * inch, 2.0 * inch], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE_2]),
                    ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            )
        )
        page.keep([table], max_height=page.remaining)

    def reference_page(page: PageLayout, part: int) -> None:
        page.heading(f"References {part} of 2", "References")
        if not sources:
            page.callout(
                "Reference register unavailable",
                "No readable sources were found in docs/research/references.json. The report must not be treated as publication-ready until the primary-source register is restored.",
                warning=True,
            )
            return
        chunks = split_evenly(sources, 2)
        chunk = chunks[part - 1]
        page.paragraph(
            f"Primary-source register reviewed before the publication baseline of {PUBLICATION_DATE}. Workstation build dates are intentionally omitted from citations.",
            "caption",
        )
        flowables: list[Any] = []
        offset = 1 if part == 1 else len(chunks[0]) + 1
        for index, source in enumerate(chunk, start=offset):
            if not isinstance(source, dict):
                flowables.append(Paragraph(f"{index}. {safe(source)}", STYLES["reference"]))
                continue
            title = source.get("title", "Untitled source")
            publisher = source.get("publisher", "Publisher not recorded")
            source_type = source.get("source_type", "source")
            url = source.get("url", "URL not recorded")
            source_id = source.get("id", f"REF-{index:02d}")
            text = (
                f"{index}. <b>{safe(source_id)}. {safe(title)}.</b> {safe(publisher)}. "
                f"{safe(source_type)}.<br/>"
                f"{safe(url)}"
            )
            flowables.append(Paragraph(text, STYLES["reference"]))
        page.keep(flowables, max_height=page.remaining)

    def page_31(page: PageLayout) -> None:
        page.heading("Limitations, roadmap, and conclusion", "11. Conclusion")
        page.subheading("Limitations")
        page.bullet("The benchmark is synthetic and focused on structural scale; it does not represent clinical diversity, prevalence, fairness, or real documentation quality.")
        page.bullet("The deterministic generator demonstrates provenance-preserving structure, not natural-language quality, coding adequacy, or clinical usefulness.")
        page.bullet("The local identity gateway, SQLite persistence, and transcript endpoint are demonstration scaffolding, not a production EHR, identity provider, speech service, or managed data platform.")
        page.bullet("Direct EHR write-back, operational monitoring, deployment penetration testing, clinician validation, and privacy impact assessment remain incomplete.")
        page.bullet("Automated test results are reportable only when evidence/tests/test_inventory.json is present and complete; any placeholder in Appendix A blocks a release claim.")
        page.subheading("Roadmap")
        page.table(
            [
                ["Stage", "Priority work", "Exit evidence"],
                ["1. Evidence maintenance", "Refresh exhaustive inventories, builds, scans, benchmark checks, and PDF QA", "Reconciled artifacts with timestamps, commands, environments, and failures"],
                ["2. Adapter hardening", "SMART discovery, issuer validation, idempotent paging, conflict and provenance behavior", "Conformance and integration tests against approved sandboxes"],
                ["3. Clinical validation", "Representative cases, blinded review, error taxonomy, acceptance thresholds", "Qualified governance approval with documented limitations"],
                ["4. Deployment readiness", "Managed identity, keys, storage, audit, monitoring, backup, incident and continuity controls", "Organization risk acceptance and verified operational controls"],
                ["5. Controlled pilot", "Limited users, monitoring, disable path, feedback and amendment workflow", "Pilot report with safety, usability, and incident findings"],
            ],
            [1.05 * inch, 3.1 * inch, 2.05 * inch],
            small=True,
        )
        page.subheading("Conclusion")
        page.paragraph(
            "The project shows that a clinical documentation copilot can be designed around explicit source constraints, plan-aware failure behavior, visible human approval, immutable completion, and reproducible synthetic evidence. Its strongest contribution is the separation of demonstrated code behavior from deployment and clinical claims. The appropriate next step is adapter hardening and qualified validation, not autonomous use."
        )
        page.callout(
            "Authorship and use statement",
            "Author: Manideep. Publication and evidence snapshot date: April 18, 2026. This report describes a research reference implementation and must not be used as a substitute for clinical judgment, legal advice, security assessment, or regulatory review.",
        )

    return [
        ("Title", page_1),
        ("Executive summary", page_2),
        ("Introduction", page_3),
        ("Research method", page_4),
        ("System design", page_5),
        ("System design", page_6),
        ("Workflow", page_7),
        ("Interoperability", page_8),
        ("Data provenance", page_9),
        ("Dataset metrics", page_10),
        ("Dataset integrity", page_11),
        ("AI safety", page_12),
        ("Voice safety", page_13),
        ("Note types", page_14),
        ("Note types", page_15),
        ("Security and privacy", page_16),
        ("Threat model", page_17),
        ("Validation", page_18),
        ("Quantitative evidence", page_19),
        ("Deployment evidence", page_20),
        ("Product walkthrough", page_21),
        ("Product walkthrough", page_22),
        ("Product walkthrough", page_23),
        ("Product walkthrough", page_24),
        ("Test appendix", lambda page: test_page(page, 1)),
        ("Test appendix", lambda page: test_page(page, 2)),
        ("Test appendix", lambda page: test_page(page, 3)),
        ("Test appendix", lambda page: test_page(page, 4)),
        ("References", lambda page: reference_page(page, 1)),
        ("References", lambda page: reference_page(page, 2)),
        ("Conclusion", page_31),
    ]


def split_evenly(items: Sequence[Any], parts: int) -> list[list[Any]]:
    """Split items into ordered, near-equal chunks while preserving every item."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    size = len(items)
    base, extra = divmod(size, parts)
    chunks: list[list[Any]] = []
    cursor = 0
    for index in range(parts):
        length = base + (1 if index < extra else 0)
        chunks.append(list(items[cursor : cursor + length]))
        cursor += length
    return chunks


def generate_report(project_root: Path, output_path: Path) -> Path:
    project_root = project_root.resolve()
    output_path = output_path if output_path.is_absolute() else project_root / output_path
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    evidence = load_evidence(project_root)
    pages = report_pages(evidence)
    if len(pages) != TOTAL_PAGES:
        raise RuntimeError(f"Report definition has {len(pages)} pages; expected exactly {TOTAL_PAGES}")

    canvas = Canvas(str(output_path), pagesize=letter, pageCompression=1)
    canvas.setDateFormatter(lambda *_: "D:20260418120000-05'00'")
    canvas.setTitle(f"{REPORT_TITLE}: {REPORT_SUBTITLE}")
    canvas.setAuthor(AUTHOR)
    canvas.setSubject("Safety-first grounded clinical documentation reference architecture and evidence report")
    canvas.setKeywords(
        "clinical documentation, grounded generation, FHIR R4, SMART, Synthea, human review, safety"
    )
    canvas.setCreator("Clinical Documentation Copilot report generator")

    for page_number, (section, renderer) in enumerate(pages, start=1):
        layout = PageLayout(canvas, page_number, section)
        layout.header_footer()
        canvas.bookmarkPage(f"page-{page_number}")
        renderer(layout)
        canvas.showPage()
    canvas.save()
    return output_path


def parse_args() -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_root,
        help="Repository root containing evidence/ and docs/research/references.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output PDF path (relative paths are resolved under --project-root)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = generate_report(args.project_root, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
