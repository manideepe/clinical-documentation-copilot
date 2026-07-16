from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from .db import Repository, utcnow
from .generator import MISSING, generate_grounded_note
from .schemas import (
    AppointmentCreate,
    AppointmentStatus,
    ClientSyncRequest,
    NoteType,
    PlanStatus,
    TextSummarySave,
    TreatmentPlanSyncRequest,
    VoiceSummarySave,
)
from .templates import validate_note


@dataclass
class DomainError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def _payload_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _newer(incoming: str, existing: str) -> bool:
    return datetime.fromisoformat(incoming) > datetime.fromisoformat(existing)


class ClinicalService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def _receipt(
        self,
        connection: sqlite3.Connection,
        operation: str,
        request_id: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM sync_receipts WHERE operation = ? AND request_id = ?",
            (operation, request_id),
        ).fetchone()
        if not row:
            return None
        if row["payload_hash"] != payload_hash:
            raise DomainError(
                409,
                "idempotency_conflict",
                "This request_id was already used with a different payload",
            )
        result = json.loads(row["result_json"])
        result["idempotent_replay"] = True
        return result

    @staticmethod
    def _store_receipt(
        connection: sqlite3.Connection,
        operation: str,
        request_id: str,
        payload_hash: str,
        result: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO sync_receipts VALUES (?, ?, ?, ?, ?)",
            (operation, request_id, payload_hash, json.dumps(result, sort_keys=True), utcnow()),
        )

    def sync_clients(self, payload: ClientSyncRequest, actor_id: str) -> dict[str, Any]:
        operation = "CLIENT_SYNC"
        digest = _payload_hash(payload)
        with self.repo.connection() as connection:
            replay = self._receipt(connection, operation, payload.request_id, digest)
            if replay:
                return replay
            counts = {"created": 0, "updated": 0, "unchanged": 0}
            now = utcnow()
            for client in payload.clients:
                incoming_updated = client.source_updated_at.isoformat()
                existing = connection.execute(
                    "SELECT * FROM clients WHERE external_id = ?", (client.external_id,)
                ).fetchone()
                values = (
                    self.repo.encrypt_text(client.given_name),
                    self.repo.encrypt_text(client.family_name),
                    self.repo.encrypt_text(client.date_of_birth.isoformat()),
                    int(client.is_active),
                    incoming_updated,
                    now,
                )
                if not existing:
                    connection.execute(
                        """INSERT INTO clients
                           (external_id, given_name_enc, family_name_enc, date_of_birth_enc,
                            is_active, source_updated_at, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (client.external_id, *values[:-1], now, now),
                    )
                    counts["created"] += 1
                elif _newer(incoming_updated, existing["source_updated_at"]):
                    connection.execute(
                        """UPDATE clients SET given_name_enc=?, family_name_enc=?,
                           date_of_birth_enc=?, is_active=?, source_updated_at=?, updated_at=?
                           WHERE external_id=?""",
                        (*values, client.external_id),
                    )
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
            result = {
                "request_id": payload.request_id,
                **counts,
                "total": len(payload.clients),
                "idempotent_replay": False,
            }
            self._store_receipt(connection, operation, payload.request_id, digest, result)
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="EHR_CLIENT_SYNC",
                resource_type="SYNC_BATCH",
                resource_id=payload.request_id,
                metadata={**counts, "total": len(payload.clients)},
            )
            return result

    def sync_plans(self, payload: TreatmentPlanSyncRequest, actor_id: str) -> dict[str, Any]:
        operation = "TREATMENT_PLAN_SYNC"
        digest = _payload_hash(payload)
        with self.repo.connection() as connection:
            replay = self._receipt(connection, operation, payload.request_id, digest)
            if replay:
                return replay
            counts = {"created": 0, "updated": 0, "unchanged": 0}
            now = utcnow()
            for plan in payload.treatment_plans:
                client = connection.execute(
                    "SELECT id FROM clients WHERE external_id = ?", (plan.client_external_id,)
                ).fetchone()
                if not client:
                    raise DomainError(
                        422,
                        "unknown_client",
                        "Treatment plan references a client that has not been synchronized",
                        {"client_external_id": plan.client_external_id},
                    )
                incoming_updated = plan.source_updated_at.isoformat()
                existing = connection.execute(
                    "SELECT * FROM treatment_plans WHERE external_id = ?", (plan.external_id,)
                ).fetchone()
                values = (
                    client["id"],
                    plan.status.value,
                    plan.effective_date.isoformat(),
                    plan.expiration_date.isoformat() if plan.expiration_date else None,
                    self.repo.encrypt_json(plan.goals),
                    self.repo.encrypt_json(plan.objectives),
                    incoming_updated,
                    now,
                )
                if not existing:
                    connection.execute(
                        """INSERT INTO treatment_plans
                           (external_id, client_id, status, effective_date, expiration_date,
                            goals_enc, objectives_enc, source_updated_at, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (plan.external_id, *values[:-1], now, now),
                    )
                    counts["created"] += 1
                elif existing["client_id"] != client["id"]:
                    raise DomainError(409, "plan_client_mismatch", "A plan cannot be reassigned to another client")
                elif _newer(incoming_updated, existing["source_updated_at"]):
                    connection.execute(
                        """UPDATE treatment_plans SET client_id=?, status=?, effective_date=?,
                           expiration_date=?, goals_enc=?, objectives_enc=?, source_updated_at=?,
                           updated_at=? WHERE external_id=?""",
                        (*values, plan.external_id),
                    )
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
            result = {
                "request_id": payload.request_id,
                **counts,
                "total": len(payload.treatment_plans),
                "idempotent_replay": False,
            }
            self._store_receipt(connection, operation, payload.request_id, digest, result)
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="EHR_TREATMENT_PLAN_SYNC",
                resource_type="SYNC_BATCH",
                resource_id=payload.request_id,
                metadata={**counts, "total": len(payload.treatment_plans)},
            )
            return result

    def _plan_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "external_id": row["external_id"],
            "status": row["status"],
            "effective_date": row["effective_date"],
            "expiration_date": row["expiration_date"],
            "goals": self.repo.decrypt_json(row["goals_enc"]),
            "objectives": self.repo.decrypt_json(row["objectives_enc"]),
            "source_updated_at": row["source_updated_at"],
        }

    def _active_plan_row(self, connection: sqlite3.Connection, client_id: int) -> sqlite3.Row | None:
        today = date.today().isoformat()
        rows = connection.execute(
            """SELECT * FROM treatment_plans
               WHERE client_id=? AND status='ACTIVE' AND effective_date<=?
                 AND (expiration_date IS NULL OR expiration_date>=?)
               ORDER BY effective_date DESC, source_updated_at DESC, id DESC LIMIT 2""",
            (client_id, today, today),
        ).fetchall()
        if len(rows) > 1 and (
            rows[0]["effective_date"], rows[0]["source_updated_at"]
        ) == (
            rows[1]["effective_date"], rows[1]["source_updated_at"]
        ):
            raise DomainError(
                409,
                "ambiguous_active_treatment_plan",
                "Multiple active treatment plans have the same effective and source update time",
            )
        return rows[0] if rows else None

    @staticmethod
    def _latest_plan_row(connection: sqlite3.Connection, client_id: int) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT * FROM treatment_plans WHERE client_id=?
               ORDER BY effective_date DESC, source_updated_at DESC, id DESC LIMIT 1""",
            (client_id,),
        ).fetchone()

    def list_clients(self) -> list[dict[str, Any]]:
        with self.repo.connection() as connection:
            rows = connection.execute("SELECT * FROM clients ORDER BY external_id").fetchall()
            result = []
            for row in rows:
                active = self._plan_dict(self._active_plan_row(connection, row["id"]))
                latest = self._plan_dict(self._latest_plan_row(connection, row["id"]))
                result.append(
                    {
                        "external_id": row["external_id"],
                        "given_name": self.repo.decrypt_text(row["given_name_enc"]),
                        "family_name": self.repo.decrypt_text(row["family_name_enc"]),
                        "date_of_birth": self.repo.decrypt_text(row["date_of_birth_enc"]),
                        "is_active": bool(row["is_active"]),
                        "active_treatment_plan": active,
                        "latest_treatment_plan": latest,
                    }
                )
            return result

    def create_appointment(self, payload: AppointmentCreate, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            client = connection.execute(
                "SELECT * FROM clients WHERE external_id=?", (payload.client_external_id,)
            ).fetchone()
            if not client or not client["is_active"]:
                raise DomainError(404, "active_client_not_found", "An active synchronized client is required")
            active_plan = self._active_plan_row(connection, client["id"])
            selection_plan = active_plan or self._latest_plan_row(connection, client["id"])
            if not selection_plan:
                raise DomainError(409, "treatment_plan_required", "A synchronized treatment plan is required")
            selected_plan = self._plan_dict(selection_plan)
            assert selected_plan is not None
            if not set(payload.treatment_goals).issubset(set(selected_plan["goals"])):
                raise DomainError(
                    422,
                    "invalid_goal_selection",
                    "Goals must come from the current active plan, or latest plan when none is active",
                )
            if not set(payload.treatment_objectives).issubset(set(selected_plan["objectives"])):
                raise DomainError(
                    422,
                    "invalid_objective_selection",
                    "Objectives must come from the current active plan, or latest plan when none is active",
                )
            appointment_id = str(uuid.uuid4())
            now = utcnow()
            connection.execute(
                """INSERT INTO appointments
                   (id, client_id, appointment_date, staff_member, service_type, note_type,
                    status, selected_goals_enc, selected_objectives_enc, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'SCHEDULED', ?, ?, ?, ?)""",
                (
                    appointment_id,
                    client["id"],
                    payload.appointment_date.isoformat(),
                    payload.staff_member,
                    payload.service_type,
                    payload.note_type.value,
                    self.repo.encrypt_json(payload.treatment_goals),
                    self.repo.encrypt_json(payload.treatment_objectives),
                    now,
                    now,
                ),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="APPOINTMENT_CREATED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
            )
        return self.get_appointment(appointment_id)

    @staticmethod
    def _appointment_row(connection: sqlite3.Connection, appointment_id: str) -> sqlite3.Row:
        row = connection.execute(
            """SELECT a.*, c.external_id AS client_external_id,
                      p.external_id AS generated_plan_external_id
               FROM appointments a JOIN clients c ON c.id=a.client_id
               LEFT JOIN treatment_plans p ON p.id=a.plan_id_at_generation
               WHERE a.id=?""",
            (appointment_id,),
        ).fetchone()
        if not row:
            raise DomainError(404, "appointment_not_found", "Appointment was not found")
        return row

    def _appointment_dict(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, Any]:
        plan = self._plan_dict(self._active_plan_row(connection, row["client_id"]))
        return {
            "id": row["id"],
            "client_external_id": row["client_external_id"],
            "appointment_date": row["appointment_date"],
            "staff_member": row["staff_member"],
            "service_type": row["service_type"],
            "note_type": row["note_type"],
            "status": row["status"],
            "documentation_method": row["documentation_method"],
            "treatment_goals": self.repo.decrypt_json(row["selected_goals_enc"]),
            "treatment_objectives": self.repo.decrypt_json(row["selected_objectives_enc"]),
            "bullet_points": self.repo.decrypt_json(row["bullet_points_enc"]),
            "transcript": self.repo.decrypt_json(row["transcript_enc"]),
            "active_treatment_plan": plan,
            "voice_allowed": plan is not None and row["locked_at"] is None,
            "generation_allowed": plan is not None and row["locked_at"] is None,
            "note_content": self.repo.decrypt_text(row["note_content_enc"]),
            "reviewed_at": row["reviewed_at"],
            "approved_at": row["approved_at"],
            "completed_at": row["completed_at"],
            "locked_at": row["locked_at"],
            "generated_with_plan_external_id": row["generated_plan_external_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_appointment(self, appointment_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            return self._appointment_dict(connection, self._appointment_row(connection, appointment_id))

    @staticmethod
    def _ensure_unlocked(row: sqlite3.Row) -> None:
        if row["locked_at"] is not None:
            raise DomainError(409, "appointment_locked", "Completed appointments are immutable")

    def _source_snapshot_hash(self, row: sqlite3.Row) -> str | None:
        method = row["documentation_method"]
        if method == "TEXT":
            source = {"method": method, "bullet_points": self.repo.decrypt_json(row["bullet_points_enc"])}
        elif method == "VOICE":
            source = {
                "method": method,
                "transcript": self.repo.decrypt_json(row["transcript_enc"]),
                "duration_seconds": row["transcript_duration_seconds"],
            }
        else:
            return None
        return _payload_hash(source)

    def start_appointment(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if row["status"] != AppointmentStatus.SCHEDULED:
                raise DomainError(409, "invalid_status_transition", "Only a scheduled appointment can be started")
            connection.execute(
                "UPDATE appointments SET status='IN_PROGRESS', updated_at=? WHERE id=?",
                (utcnow(), appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="APPOINTMENT_STARTED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
                metadata={"active_plan_available": self._active_plan_row(connection, row["client_id"]) is not None},
            )
        return self.get_appointment(appointment_id)

    def cancel_appointment(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if row["status"] not in {AppointmentStatus.SCHEDULED, AppointmentStatus.IN_PROGRESS}:
                raise DomainError(
                    409,
                    "invalid_status_transition",
                    "Only a scheduled or in-progress appointment can be cancelled",
                )
            now = utcnow()
            connection.execute(
                """UPDATE appointments SET status='CANCELLED', locked_at=?, updated_at=?
                   WHERE id=?""",
                (now, now, appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="APPOINTMENT_CANCELLED_AND_LOCKED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
            )
        return self.get_appointment(appointment_id)

    def save_text_summary(
        self, appointment_id: str, payload: TextSummarySave, actor_id: str
    ) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if row["status"] not in {AppointmentStatus.IN_PROGRESS, AppointmentStatus.DOCUMENTATION_PENDING}:
                raise DomainError(409, "invalid_appointment_status", "Appointment must be in progress")
            if row["approved_at"]:
                raise DomainError(409, "approved_note_source_locked", "Source facts cannot change after approval")
            connection.execute(
                """UPDATE appointments SET documentation_method='TEXT', bullet_points_enc=?,
                   transcript_enc=NULL, transcript_duration_seconds=NULL,
                   status='DOCUMENTATION_PENDING', note_content_enc=NULL,
                   plan_id_at_generation=NULL, plan_snapshot_hash_at_generation=NULL,
                   source_snapshot_hash_at_generation=NULL,
                   generated_at=NULL,
                   reviewed_at=NULL, reviewed_by=NULL, approved_at=NULL, approved_by=NULL,
                   updated_at=? WHERE id=?""",
                (self.repo.encrypt_json(payload.bullet_points), utcnow(), appointment_id),
            )
            active = self._active_plan_row(connection, row["client_id"])
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="TEXT_SUMMARY_SAVED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
                metadata={"bullet_count": len(payload.bullet_points), "generation_deferred": active is None},
            )
        return self.get_appointment(appointment_id)

    def save_voice_summary(
        self, appointment_id: str, payload: VoiceSummarySave, actor_id: str
    ) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if not self._active_plan_row(connection, row["client_id"]):
                raise DomainError(
                    409,
                    "voice_disabled_expired_plan",
                    "Voice capture, upload, processing, and storage are disabled until an active plan exists",
                )
            if row["status"] not in {AppointmentStatus.IN_PROGRESS, AppointmentStatus.DOCUMENTATION_PENDING}:
                raise DomainError(409, "invalid_appointment_status", "Appointment must be in progress")
            if payload.duration_seconds < 300:
                raise DomainError(
                    422,
                    "recording_too_short",
                    "Voice documentation requires at least 300 seconds; nothing was stored",
                )
            turns = [turn.model_dump() for turn in payload.transcript]
            connection.execute(
                """UPDATE appointments SET documentation_method='VOICE', bullet_points_enc=NULL,
                   transcript_enc=?, transcript_duration_seconds=?, status='DOCUMENTATION_PENDING',
                   note_content_enc=NULL, plan_id_at_generation=NULL, generated_at=NULL,
                   plan_snapshot_hash_at_generation=NULL,
                   source_snapshot_hash_at_generation=NULL,
                   reviewed_at=NULL, reviewed_by=NULL, approved_at=NULL, approved_by=NULL,
                   updated_at=? WHERE id=?""",
                (self.repo.encrypt_json(turns), payload.duration_seconds, utcnow(), appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="DIARIZED_TRANSCRIPT_SAVED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
                metadata={"duration_seconds": payload.duration_seconds, "turn_count": len(turns), "audio_stored": False},
            )
        return self.get_appointment(appointment_id)

    def generate_note(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if row["status"] != AppointmentStatus.DOCUMENTATION_PENDING:
                raise DomainError(409, "documentation_not_ready", "Save a documentation summary before generation")
            if row["approved_at"]:
                raise DomainError(409, "note_already_approved", "An approved note cannot be regenerated")
            plan_row = self._active_plan_row(connection, row["client_id"])
            if not plan_row:
                raise DomainError(
                    409,
                    "generation_deferred_treatment_plan",
                    "Documentation is pending until a new active treatment plan is synchronized",
                )
            appointment = self._appointment_dict(connection, row)
            method = row["documentation_method"]
            if method == "TEXT":
                source_facts = appointment["bullet_points"] or []
                source_label = "Clinician-entered bullet points"
            elif method == "VOICE":
                transcript = appointment["transcript"] or []
                source_facts = [f"{turn['speaker']}: {turn['text']}" for turn in transcript]
                source_label = "Diarized transcript"
            else:
                raise DomainError(422, "documentation_source_required", "No supported source facts were saved")
            if not source_facts:
                raise DomainError(422, "documentation_source_required", "No supplied facts are available")
            plan = self._plan_dict(plan_row)
            assert plan is not None
            plan_snapshot_hash = _payload_hash(plan)
            source_snapshot_hash = self._source_snapshot_hash(row)
            if source_snapshot_hash is None:
                raise DomainError(422, "documentation_source_required", "No supplied facts are available")
            note = generate_grounded_note(
                note_type=NoteType(row["note_type"]),
                appointment=appointment,
                treatment_plan=plan,
                source_facts=source_facts,
                source_label=source_label,
            )
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS next FROM note_revisions WHERE appointment_id=?",
                (appointment_id,),
            ).fetchone()["next"]
            now = utcnow()
            connection.execute(
                """UPDATE appointments SET note_content_enc=?, plan_id_at_generation=?,
                   plan_snapshot_hash_at_generation=?, generated_at=?,
                   source_snapshot_hash_at_generation=?,
                   reviewed_at=NULL, reviewed_by=NULL, approved_at=NULL,
                   approved_by=NULL, updated_at=? WHERE id=?""",
                (
                    self.repo.encrypt_text(note),
                    plan_row["id"],
                    plan_snapshot_hash,
                    now,
                    source_snapshot_hash,
                    now,
                    appointment_id,
                ),
            )
            connection.execute(
                """INSERT INTO note_revisions
                   (appointment_id, revision, action, content_enc, editor_id, created_at)
                   VALUES (?, ?, 'GENERATED', ?, ?, ?)""",
                (appointment_id, revision, self.repo.encrypt_text(note), actor_id, now),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="NOTE_GENERATED_DETERMINISTICALLY",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
                metadata={"revision": revision, "plan_external_id": plan["external_id"], "source_method": method},
            )
        return self.get_appointment(appointment_id)

    def edit_note(self, appointment_id: str, content: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if not row["note_content_enc"]:
                raise DomainError(409, "note_not_generated", "Generate a note before editing")
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS next FROM note_revisions WHERE appointment_id=?",
                (appointment_id,),
            ).fetchone()["next"]
            now = utcnow()
            encrypted = self.repo.encrypt_text(content)
            connection.execute(
                """UPDATE appointments SET note_content_enc=?, reviewed_at=NULL, reviewed_by=NULL,
                   approved_at=NULL, approved_by=NULL, updated_at=? WHERE id=?""",
                (encrypted, now, appointment_id),
            )
            connection.execute(
                """INSERT INTO note_revisions
                   (appointment_id, revision, action, content_enc, editor_id, created_at)
                   VALUES (?, ?, 'EDITED', ?, ?, ?)""",
                (appointment_id, revision, encrypted, actor_id, now),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="NOTE_EDITED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
                metadata={"revision": revision},
            )
        return self.get_appointment(appointment_id)

    def mark_reviewed(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if not row["note_content_enc"]:
                raise DomainError(409, "note_not_generated", "A generated note is required")
            now = utcnow()
            connection.execute(
                "UPDATE appointments SET reviewed_at=?, reviewed_by=?, updated_at=? WHERE id=?",
                (now, actor_id, now, appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="NOTE_REVIEWED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
            )
        return self.get_appointment(appointment_id)

    def approve_note(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if not row["reviewed_at"]:
                raise DomainError(409, "review_required", "Staff review is required before approval")
            current_plan = self._active_plan_row(connection, row["client_id"])
            current_plan_snapshot = self._plan_dict(current_plan)
            if (
                not current_plan
                or current_plan["id"] != row["plan_id_at_generation"]
                or not current_plan_snapshot
                or _payload_hash(current_plan_snapshot) != row["plan_snapshot_hash_at_generation"]
                or self._source_snapshot_hash(row) != row["source_snapshot_hash_at_generation"]
            ):
                raise DomainError(
                    409,
                    "stale_generation_plan",
                    "The active treatment plan changed after generation; regenerate and review a new draft",
                )
            content = self.repo.decrypt_text(row["note_content_enc"]) or ""
            errors = validate_note(NoteType(row["note_type"]), content)
            if MISSING in content:
                errors.append("unresolved_clinician_documentation")
            if errors:
                raise DomainError(422, "note_validation_failed", "Required documentation is incomplete", {"errors": errors})
            now = utcnow()
            connection.execute(
                "UPDATE appointments SET approved_at=?, approved_by=?, updated_at=? WHERE id=?",
                (now, actor_id, now, appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="NOTE_APPROVED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
            )
        return self.get_appointment(appointment_id)

    def complete_appointment(self, appointment_id: str, actor_id: str) -> dict[str, Any]:
        with self.repo.connection() as connection:
            row = self._appointment_row(connection, appointment_id)
            self._ensure_unlocked(row)
            if not row["note_content_enc"] or not row["reviewed_at"] or not row["approved_at"]:
                raise DomainError(
                    409,
                    "completion_requirements_not_met",
                    "A generated, reviewed, approved, and valid note is required",
                )
            current_plan = self._active_plan_row(connection, row["client_id"])
            current_plan_snapshot = self._plan_dict(current_plan)
            if (
                not current_plan
                or current_plan["id"] != row["plan_id_at_generation"]
                or not current_plan_snapshot
                or _payload_hash(current_plan_snapshot) != row["plan_snapshot_hash_at_generation"]
                or self._source_snapshot_hash(row) != row["source_snapshot_hash_at_generation"]
            ):
                raise DomainError(
                    409,
                    "stale_generation_plan",
                    "The active treatment plan changed after generation; regenerate and review a new draft",
                )
            content = self.repo.decrypt_text(row["note_content_enc"]) or ""
            errors = validate_note(NoteType(row["note_type"]), content)
            if MISSING in content:
                errors.append("unresolved_clinician_documentation")
            if errors:
                raise DomainError(422, "note_validation_failed", "Required documentation is incomplete", {"errors": errors})
            now = utcnow()
            connection.execute(
                """UPDATE appointments SET status='COMPLETED', completed_at=?, locked_at=?,
                   updated_at=? WHERE id=?""",
                (now, now, now, appointment_id),
            )
            self.repo.audit(
                connection,
                actor_id=actor_id,
                action="APPOINTMENT_COMPLETED_AND_LOCKED",
                resource_type="APPOINTMENT",
                resource_id=appointment_id,
            )
        return self.get_appointment(appointment_id)

    def revisions(self, appointment_id: str) -> list[dict[str, Any]]:
        with self.repo.connection() as connection:
            self._appointment_row(connection, appointment_id)
            rows = connection.execute(
                "SELECT * FROM note_revisions WHERE appointment_id=? ORDER BY revision",
                (appointment_id,),
            ).fetchall()
            return [
                {
                    "revision": row["revision"],
                    "action": row["action"],
                    "content": self.repo.decrypt_text(row["content_enc"]),
                    "editor_id": row["editor_id"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.repo.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "occurred_at": row["occurred_at"],
                    "actor_id": row["actor_id"],
                    "action": row["action"],
                    "resource_type": row["resource_type"],
                    "resource_id": row["resource_id"],
                    "outcome": row["outcome"],
                    "metadata": json.loads(row["metadata_json"]),
                    "previous_hash": row["previous_hash"],
                    "entry_hash": row["entry_hash"],
                }
                for row in rows
            ]
