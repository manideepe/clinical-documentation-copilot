from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"


class AppointmentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    DOCUMENTATION_PENDING = "DOCUMENTATION_PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NoteType(StrEnum):
    CASE_MANAGEMENT = "CASE_MANAGEMENT"
    INITIAL_CHILD_ASSESSMENT = "INITIAL_CHILD_ASSESSMENT"
    CHILD_ASSESSMENT_UPDATE = "CHILD_ASSESSMENT_UPDATE"
    INITIAL_ADULT_ASSESSMENT = "INITIAL_ADULT_ASSESSMENT"
    ADULT_ASSESSMENT_UPDATE = "ADULT_ASSESSMENT_UPDATE"
    COUNSELOR = "COUNSELOR"
    EVALUATION_AND_MANAGEMENT = "EVALUATION_AND_MANAGEMENT"
    NURSING_PROGRESS = "NURSING_PROGRESS"


class ClientSyncItem(StrictModel):
    external_id: str = Field(min_length=1, max_length=128)
    given_name: str = Field(min_length=1, max_length=100)
    family_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    is_active: bool = True
    source_updated_at: AwareDatetime


class ClientSyncRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=128)
    clients: list[ClientSyncItem] = Field(min_length=1, max_length=1000)


class TreatmentPlanSyncItem(StrictModel):
    external_id: str = Field(min_length=1, max_length=128)
    client_external_id: str = Field(min_length=1, max_length=128)
    status: PlanStatus
    effective_date: date
    expiration_date: date | None = None
    goals: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=50)
    objectives: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=100)
    source_updated_at: AwareDatetime

    @field_validator("goals", "objectives")
    @classmethod
    def reject_blank_list_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("List items cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "TreatmentPlanSyncItem":
        if self.expiration_date and self.expiration_date < self.effective_date:
            raise ValueError("expiration_date cannot precede effective_date")
        return self


class TreatmentPlanSyncRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=128)
    treatment_plans: list[TreatmentPlanSyncItem] = Field(min_length=1, max_length=1000)


class AppointmentCreate(StrictModel):
    client_external_id: str = Field(min_length=1, max_length=128)
    appointment_date: AwareDatetime
    staff_member: str = Field(min_length=1, max_length=128)
    service_type: str = Field(min_length=1, max_length=128)
    note_type: NoteType
    treatment_goals: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=20)
    treatment_objectives: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=30)

    @field_validator("treatment_goals", "treatment_objectives")
    @classmethod
    def reject_blanks(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Treatment selections cannot be blank")
        return cleaned


class TextSummarySave(StrictModel):
    # Source bullets are evidentiary input. Validate a normalized view, but store
    # and return the caller's exact strings without trimming or prefix removal.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    bullet_points: list[Annotated[str, Field(min_length=3, max_length=2000)]] = Field(min_length=6, max_length=7)

    @field_validator("bullet_points")
    @classmethod
    def clean_bullets(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(len(value) < 3 for value in normalized):
            raise ValueError("Each bullet point must contain a meaningful supplied fact")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate bullet points are not allowed")
        return values


class TranscriptTurn(StrictModel):
    speaker: str
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("speaker")
    @classmethod
    def supported_speaker(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"STAFF", "CLIENT"}:
            raise ValueError("speaker must be STAFF or CLIENT")
        return normalized


class VoiceSummarySave(StrictModel):
    duration_seconds: int = Field(ge=1, le=14400)
    transcript: list[TranscriptTurn] = Field(min_length=2, max_length=1000)

    @model_validator(mode="after")
    def both_speakers_are_present(self) -> "VoiceSummarySave":
        if {turn.speaker for turn in self.transcript} != {"STAFF", "CLIENT"}:
            raise ValueError("Transcript must contain both STAFF and CLIENT turns")
        return self


class NoteEdit(StrictModel):
    content: str = Field(min_length=20, max_length=100000)


class AppointmentView(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    id: str
    client_external_id: str
    appointment_date: str
    staff_member: str
    service_type: str
    note_type: NoteType
    status: AppointmentStatus
    documentation_method: str | None
    treatment_goals: list[str]
    treatment_objectives: list[str]
    bullet_points: list[str] | None
    transcript: list[dict[str, str]] | None
    active_treatment_plan: dict | None
    voice_allowed: bool
    generation_allowed: bool
    note_content: str | None
    reviewed_at: str | None
    approved_at: str | None
    completed_at: str | None
    locked_at: str | None
    generated_with_plan_external_id: str | None
    created_at: str
    updated_at: str
