from __future__ import annotations

from typing import Any

from .schemas import NoteType
from .templates import TEMPLATES


MISSING = "[Additional clinician documentation required; no supported fact was supplied.]"


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def generate_grounded_note(
    *,
    note_type: NoteType,
    appointment: dict[str, Any],
    treatment_plan: dict[str, Any],
    source_facts: list[str],
    source_label: str,
) -> str:
    """Create a deterministic review draft without statistical generation.

    Every clinical proposition in the output is copied from an allowed source.
    The function adds labels, structure, and explicit missing-data markers only.
    """
    template = TEMPLATES[note_type]
    sections: list[str] = [
        f"# {template.display_name}",
        "",
        "## Document Control",
        f"- Appointment date: {appointment['appointment_date']}",
        f"- Service type: {appointment['service_type']}",
        f"- Staff member: {appointment['staff_member']}",
        f"- Source method: {source_label}",
        f"- Treatment plan: {treatment_plan['external_id']}",
        "",
    ]
    for index, heading in enumerate(template.sections):
        sections.extend((f"## {heading}", ""))
        if index == 0:
            sections.extend(("Supplied appointment facts:", _bullets(source_facts)))
        elif index == 1:
            sections.extend(
                (
                    "Goals from the latest active treatment plan:",
                    _bullets(treatment_plan["goals"]),
                    "",
                    "Objectives from the latest active treatment plan:",
                    _bullets(treatment_plan["objectives"]),
                )
            )
        else:
            sections.append(MISSING)
        sections.append("")
    sections.extend(
        (
            "## Clinician Review Notice",
            "This deterministic draft reorganizes supplied facts only. A qualified clinician must "
            "verify, edit, and approve it before use in the EHR.",
        )
    )
    return "\n".join(sections).strip() + "\n"
