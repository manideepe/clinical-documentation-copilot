from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def api(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        yield client


def auth_headers(role: str = "ADMINISTRATOR", user_id: str = "test-user") -> dict[str, str]:
    return {
        "X-Internal-Auth": "local-development-gateway",
        "X-User-ID": user_id,
        "X-Role": role,
        "X-Session-Expires-At": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


@pytest.fixture()
def headers():
    return auth_headers()


@pytest.fixture()
def bullets():
    return [
        "Clinician reviewed the weekly schedule supplied by the client.",
        "Client identified transportation as a barrier to the next appointment.",
        "Clinician provided the clinic telephone number.",
        "Client reported attending the scheduled community program.",
        "The treatment goal was discussed during the session.",
        "Client requested a follow-up appointment next week.",
    ]


def sync_client(api: TestClient, headers: dict[str, str], *, request_id: str = "clients-0001"):
    return api.post(
        "/api/v1/ehr-sync/clients",
        headers=headers,
        json={
            "request_id": request_id,
            "clients": [
                {
                    "external_id": "EHR-C-100",
                    "given_name": "Alex",
                    "family_name": "Example",
                    "date_of_birth": "1990-02-03",
                    "is_active": True,
                    "source_updated_at": "2026-01-01T12:00:00Z",
                }
            ],
        },
    )


def sync_plan(
    api: TestClient,
    headers: dict[str, str],
    *,
    request_id: str,
    external_id: str,
    status: str,
    effective_date: str,
    expiration_date: str | None,
    goal: str,
    objective: str,
    source_updated_at: str = "2026-01-02T12:00:00Z",
):
    return api.post(
        "/api/v1/ehr-sync/treatment-plans",
        headers=headers,
        json={
            "request_id": request_id,
            "treatment_plans": [
                {
                    "external_id": external_id,
                    "client_external_id": "EHR-C-100",
                    "status": status,
                    "effective_date": effective_date,
                    "expiration_date": expiration_date,
                    "goals": [goal],
                    "objectives": [objective],
                    "source_updated_at": source_updated_at,
                }
            ],
        },
    )


def create_appointment(
    api: TestClient,
    headers: dict[str, str],
    *,
    goal: str,
    objective: str,
    note_type: str = "CASE_MANAGEMENT",
):
    return api.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "client_external_id": "EHR-C-100",
            "appointment_date": "2026-04-15T14:00:00-05:00",
            "staff_member": "test-clinician",
            "service_type": "Community support",
            "note_type": note_type,
            "treatment_goals": [goal],
            "treatment_objectives": [objective],
        },
    )
