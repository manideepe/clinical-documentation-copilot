from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from conftest import auth_headers, sync_client, sync_plan
from app.main import create_app


def test_health_is_non_sensitive_and_sets_security_headers(api):
    response = api.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["generation_mode"] == "deterministic_local"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_local_browser_origin_is_explicitly_allowed(api):
    response = api.options(
        "/api/v1/clients",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Internal-Auth,X-User-ID,X-Role,X-Session-Expires-At",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_oversized_declared_request_is_rejected_before_parsing(api, headers):
    response = api.post(
        "/api/v1/ehr-sync/clients",
        headers={**headers, "Content-Length": str(9 * 1024 * 1024)},
        content=b"{}",
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_production_rejects_missing_or_shared_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("EHR_ENVIRONMENT", "production")
    for name in ("EHR_DATA_KEY", "EHR_AUDIT_KEY", "EHR_GATEWAY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="Production requires independent secrets"):
        create_app(tmp_path / "missing-secrets.sqlite3")

    shared = "x" * 40
    monkeypatch.setenv("EHR_DATA_KEY", shared)
    monkeypatch.setenv("EHR_AUDIT_KEY", shared)
    monkeypatch.setenv("EHR_GATEWAY_TOKEN", shared)
    with pytest.raises(ValueError, match="must be independent"):
        create_app(tmp_path / "shared-secrets.sqlite3")


def test_identity_gateway_and_session_expiry_are_enforced(api):
    assert api.get("/api/v1/clients").status_code == 401
    expired = auth_headers()
    expired["X-Session-Expires-At"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    response = api.get("/api/v1/clients", headers=expired)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"


def test_role_permissions_deny_ehr_sync_to_clinician(api):
    response = sync_client(api, auth_headers("COUNSELOR"))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "permission_denied"


def test_client_sync_is_idempotent_and_request_ids_cannot_be_reused(api, headers):
    first = sync_client(api, headers)
    replay = sync_client(api, headers)
    assert first.status_code == 200
    assert first.json()["created"] == 1
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True

    changed_payload = {
        "request_id": "clients-0001",
        "clients": [
            {
                "external_id": "EHR-C-100",
                "given_name": "Changed",
                "family_name": "Example",
                "date_of_birth": "1990-02-03",
                "is_active": True,
                "source_updated_at": "2026-02-01T12:00:00Z",
            }
        ],
    }
    conflict = api.post("/api/v1/ehr-sync/clients", headers=headers, json=changed_payload)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert len(api.get("/api/v1/clients", headers=headers).json()["items"]) == 1


def test_latest_effective_active_plan_is_selected(api, headers):
    assert sync_client(api, headers).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-old-01",
        external_id="PLAN-OLD",
        status="ACTIVE",
        effective_date="2024-01-01",
        expiration_date="2030-01-01",
        goal="Old goal",
        objective="Old objective",
    ).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-new-01",
        external_id="PLAN-NEW",
        status="ACTIVE",
        effective_date="2026-01-01",
        expiration_date="2030-01-01",
        goal="Newest goal",
        objective="Newest objective",
        source_updated_at="2026-02-01T12:00:00Z",
    ).status_code == 200
    client = api.get("/api/v1/clients", headers=headers).json()["items"][0]
    assert client["active_treatment_plan"]["external_id"] == "PLAN-NEW"


def test_equally_current_active_plans_fail_closed(api, headers):
    assert sync_client(api, headers).status_code == 200
    for suffix in ("A", "B"):
        assert sync_plan(
            api,
            headers,
            request_id=f"plans-ambiguous-{suffix}",
            external_id=f"PLAN-AMBIGUOUS-{suffix}",
            status="ACTIVE",
            effective_date="2026-01-01",
            expiration_date="2030-01-01",
            goal=f"Goal {suffix}",
            objective=f"Objective {suffix}",
            source_updated_at="2026-01-02T12:00:00Z",
        ).status_code == 200
    response = api.get("/api/v1/clients", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ambiguous_active_treatment_plan"


def test_all_eight_note_templates_expose_distinct_contracts(api, headers):
    response = api.get("/api/v1/note-types", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 8
    assert len({item["note_type"] for item in items}) == 8
    assert all(item["sections"] and item["required_fields"] and item["prompt_policy"] for item in items)
    assert len({tuple(item["required_fields"]) for item in items}) == 8
    assert len({item["prompt_policy"] for item in items}) == 8


def test_stale_client_update_cannot_overwrite_newer_source_record(api, headers):
    assert sync_client(api, headers).status_code == 200
    stale = api.post(
        "/api/v1/ehr-sync/clients",
        headers=headers,
        json={
            "request_id": "clients-stale-01",
            "clients": [
                {
                    "external_id": "EHR-C-100",
                    "given_name": "Stale name",
                    "family_name": "Stale family",
                    "date_of_birth": "1990-02-03",
                    "is_active": True,
                    "source_updated_at": "2025-12-01T12:00:00Z",
                }
            ],
        },
    )
    assert stale.status_code == 200
    assert stale.json()["unchanged"] == 1
    client = api.get("/api/v1/clients", headers=headers).json()["items"][0]
    assert client["given_name"] == "Alex"


def test_protected_client_and_plan_fields_are_not_plaintext_in_sqlite(api, headers):
    assert sync_client(api, headers).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-encryption-1",
        external_id="PLAN-ENCRYPTED",
        status="ACTIVE",
        effective_date="2026-01-01",
        expiration_date="2030-01-01",
        goal="Sensitive treatment goal",
        objective="Sensitive treatment objective",
    ).status_code == 200
    with sqlite3.connect(api.app.state.settings.database_path) as connection:
        client_row = connection.execute(
            "SELECT given_name_enc, family_name_enc, date_of_birth_enc FROM clients"
        ).fetchone()
        plan_row = connection.execute(
            "SELECT goals_enc, objectives_enc FROM treatment_plans"
        ).fetchone()
    protected_values = " ".join((*client_row, *plan_row))
    for plaintext in (
        "Alex",
        "Example",
        "1990-02-03",
        "Sensitive treatment goal",
        "Sensitive treatment objective",
    ):
        assert plaintext not in protected_values


def test_audit_events_form_a_hash_chain_and_contain_no_client_names(api, headers):
    assert sync_client(api, headers).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-audit-01",
        external_id="PLAN-AUDIT",
        status="ACTIVE",
        effective_date="2026-01-01",
        expiration_date="2030-01-01",
        goal="Audit test goal",
        objective="Audit test objective",
    ).status_code == 200
    events = api.get("/api/v1/audit-events", headers=headers).json()["items"]
    assert len(events) == 2
    assert events[0]["previous_hash"] == events[1]["entry_hash"]
    serialized = str(events)
    assert "Alex" not in serialized
    assert "Example" not in serialized
