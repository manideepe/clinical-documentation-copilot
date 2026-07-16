from __future__ import annotations

from dataclasses import asdict, dataclass

from .schemas import NoteType


@dataclass(frozen=True)
class NoteTemplate:
    note_type: NoteType
    display_name: str
    sections: tuple[str, ...]
    required_fields: tuple[str, ...]
    documentation_style: str
    prompt_policy: str

    def public(self) -> dict:
        value = asdict(self)
        value["note_type"] = self.note_type.value
        value["sections"] = list(self.sections)
        value["required_fields"] = list(self.required_fields)
        return value


GROUNDING_POLICY = (
    "Use only appointment facts, the latest active treatment plan, and clinician-supplied "
    "bullets or diarized transcript. Never infer diagnoses, quotations, symptoms, progress, "
    "interventions, risk findings, or outcomes. Mark missing information for clinician input."
)


def _prompt(instruction: str) -> str:
    return f"{instruction} {GROUNDING_POLICY}"


TEMPLATES: dict[NoteType, NoteTemplate] = {
    NoteType.CASE_MANAGEMENT: NoteTemplate(
        NoteType.CASE_MANAGEMENT,
        "Case Management Note",
        ("Service Context", "Treatment Plan Alignment", "Services and Coordination", "Client Response", "Next Steps"),
        ("appointment_date", "service_type", "care_coordination_actions", "goals", "objectives", "client_response", "next_steps"),
        "Concise, objective case-management documentation focused on coordination and access.",
        _prompt("Organize supplied facts around concrete coordination, access barriers, referrals, and next actions."),
    ),
    NoteType.INITIAL_CHILD_ASSESSMENT: NoteTemplate(
        NoteType.INITIAL_CHILD_ASSESSMENT,
        "Initial Child Assessment",
        ("Assessment Context", "Presenting Information", "Developmental and Family Context", "Strengths and Needs", "Plan"),
        ("appointment_date", "presenting_information", "developmental_context", "family_context", "strengths", "needs", "initial_plan"),
        "Developmentally appropriate, neutral assessment language with no inferred history.",
        _prompt("Separate child, caregiver, developmental, family, strength, and need information when each is explicitly supplied."),
    ),
    NoteType.CHILD_ASSESSMENT_UPDATE: NoteTemplate(
        NoteType.CHILD_ASSESSMENT_UPDATE,
        "Child Assessment Update",
        ("Update Context", "Current Information", "Changes Since Prior Assessment", "Treatment Plan Alignment", "Recommendations"),
        ("appointment_date", "current_information", "supplied_changes", "goals", "objectives", "recommendations"),
        "Focused update language; changes and progress are documented only when explicitly supplied.",
        _prompt("Describe only explicitly supplied changes since the prior child assessment and avoid inferred comparison."),
    ),
    NoteType.INITIAL_ADULT_ASSESSMENT: NoteTemplate(
        NoteType.INITIAL_ADULT_ASSESSMENT,
        "Initial Adult Assessment",
        ("Assessment Context", "Presenting Information", "Relevant History", "Strengths and Needs", "Initial Plan"),
        ("appointment_date", "presenting_information", "relevant_history", "strengths", "needs", "initial_plan"),
        "Neutral initial-assessment language that separates supplied facts from missing information.",
        _prompt("Separate adult presenting information, relevant supplied history, strengths, needs, and initial plan."),
    ),
    NoteType.ADULT_ASSESSMENT_UPDATE: NoteTemplate(
        NoteType.ADULT_ASSESSMENT_UPDATE,
        "Adult Assessment Update",
        ("Update Context", "Current Information", "Reported Changes", "Treatment Plan Alignment", "Plan"),
        ("appointment_date", "current_information", "reported_changes", "goals", "objectives", "updated_plan"),
        "Focused reassessment language with no unsupported comparison or clinical conclusion.",
        _prompt("Document only supplied adult reassessment changes and distinguish report from observation."),
    ),
    NoteType.COUNSELOR: NoteTemplate(
        NoteType.COUNSELOR,
        "Counselor Note",
        ("Session Context", "Goals and Objectives Addressed", "Interventions", "Client Response", "Plan"),
        ("appointment_date", "service_type", "goals", "objectives", "interventions", "client_response", "plan"),
        "Professional counseling note language; interventions and response require explicit support.",
        _prompt("Connect only supplied counseling interventions and client response to the selected objectives."),
    ),
    NoteType.EVALUATION_AND_MANAGEMENT: NoteTemplate(
        NoteType.EVALUATION_AND_MANAGEMENT,
        "Evaluation and Management (E&M) Note",
        ("Encounter Context", "History Supplied", "Examination and Data", "Assessment", "Plan"),
        ("appointment_date", "history_supplied", "examination_data", "assessment", "medical_decision_information", "plan"),
        "Structured E&M review draft; never infer examination, diagnosis, code, or medical decision making.",
        _prompt("Keep history, examination/data, assessment, decision information, and plan distinct; insert missing markers rather than infer."),
    ),
    NoteType.NURSING_PROGRESS: NoteTemplate(
        NoteType.NURSING_PROGRESS,
        "Nursing Progress Note",
        ("Encounter Context", "Subjective Information", "Objective Information", "Nursing Actions and Response", "Plan"),
        ("appointment_date", "subjective_information", "objective_information", "nursing_actions", "response", "plan"),
        "Objective nursing documentation; vitals, medication, assessment, and response must be supplied.",
        _prompt("Separate subjective report, objective supplied measurements, nursing actions, response, and plan."),
    ),
}


def validate_note(note_type: NoteType, content: str) -> list[str]:
    errors: list[str] = []
    template = TEMPLATES[note_type]
    if not content.strip():
        errors.append("note_content_required")
        return errors
    if not content.lstrip().startswith(f"# {template.display_name}"):
        errors.append("note_title_mismatch")
    required_control_labels = (
        "Appointment date",
        "Service type",
        "Staff member",
        "Source method",
        "Treatment plan",
    )
    for label in required_control_labels:
        matching = [line for line in content.splitlines() if line.startswith(f"- {label}:")]
        if not matching or not matching[0].split(":", 1)[1].strip():
            errors.append(f"missing_document_control:{label.lower().replace(' ', '_')}")

    lines = content.splitlines()
    section_positions = {
        line[3:]: index for index, line in enumerate(lines) if line.startswith("## ")
    }
    for section in template.sections:
        start = section_positions.get(section)
        if start is None:
            errors.append(f"missing_section:{section}")
            continue
        body: list[str] = []
        for line in lines[start + 1 :]:
            if line.startswith("## "):
                break
            if line.strip():
                body.append(line.strip())
        if len(" ".join(body)) < 12:
            errors.append(f"empty_section:{section}")
    return errors
