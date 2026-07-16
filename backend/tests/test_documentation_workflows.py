from __future__ import annotations

from conftest import create_appointment, sync_client, sync_plan


def seed_active(api, headers):
    assert sync_client(api, headers).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-active-1",
        external_id="PLAN-ACTIVE",
        status="ACTIVE",
        effective_date="2026-01-01",
        expiration_date="2030-01-01",
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    ).status_code == 200


def test_text_note_happy_path_grounding_review_approval_lock_and_history(api, headers, bullets):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    assert created.status_code == 201
    appointment_id = created.json()["id"]
    assert api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers).status_code == 200
    saved = api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    assert saved.status_code == 200
    generated = api.post(
        f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers
    )
    assert generated.status_code == 200
    body = generated.json()
    note = body["note_content"]
    assert body["generated_with_plan_external_id"] == "PLAN-ACTIVE"
    assert all(fact in note for fact in bullets)
    assert "Improve appointment participation" in note
    assert "Identify one transportation strategy" in note
    assert "[Additional clinician documentation required" in note

    # Generated missing-data markers force a human edit before approval.
    assert api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers).status_code == 200
    incomplete = api.post(f"/api/v1/appointments/{appointment_id}/approve", headers=headers)
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "note_validation_failed"

    finalized = note.replace(
        "[Additional clinician documentation required; no supported fact was supplied.]",
        "Clinician reviewed this section and documented no additional supplied information.",
    )
    edited = api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": finalized},
    )
    assert edited.status_code == 200
    assert edited.json()["reviewed_at"] is None
    assert api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers).status_code == 200
    assert api.post(f"/api/v1/appointments/{appointment_id}/approve", headers=headers).status_code == 200

    # A pre-completion edit remains possible and invalidates both attestations.
    pre_completion_edit = api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": finalized + "\nClinician-added final clarification."},
    )
    assert pre_completion_edit.status_code == 200
    assert pre_completion_edit.json()["reviewed_at"] is None
    assert pre_completion_edit.json()["approved_at"] is None
    assert api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers).status_code == 200
    assert api.post(f"/api/v1/appointments/{appointment_id}/approve", headers=headers).status_code == 200
    completed = api.post(f"/api/v1/appointments/{appointment_id}/complete", headers=headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["locked_at"]

    locked_edit = api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": finalized + "\nLate mutation."},
    )
    assert locked_edit.status_code == 409
    assert locked_edit.json()["error"]["code"] == "appointment_locked"
    revisions = api.get(
        f"/api/v1/appointments/{appointment_id}/revisions", headers=headers
    ).json()["items"]
    assert [(item["revision"], item["action"]) for item in revisions] == [
        (1, "GENERATED"),
        (2, "EDITED"),
        (3, "EDITED"),
    ]


def test_expired_plan_disables_voice_and_defers_generation_until_new_plan(api, headers, bullets):
    assert sync_client(api, headers).status_code == 200
    assert sync_plan(
        api,
        headers,
        request_id="plans-expired-1",
        external_id="PLAN-EXPIRED",
        status="EXPIRED",
        effective_date="2020-01-01",
        expiration_date="2021-01-01",
        goal="Historical goal",
        objective="Historical objective",
    ).status_code == 200
    created = create_appointment(
        api,
        headers,
        goal="Historical goal",
        objective="Historical objective",
    )
    appointment_id = created.json()["id"]
    started = api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["voice_allowed"] is False

    voice = api.put(
        f"/api/v1/appointments/{appointment_id}/voice-summary",
        headers=headers,
        json={
            "duration_seconds": 600,
            "transcript": [
                {"speaker": "STAFF", "text": "Question supplied."},
                {"speaker": "CLIENT", "text": "Answer supplied."},
            ],
        },
    )
    assert voice.status_code == 409
    assert voice.json()["error"]["code"] == "voice_disabled_expired_plan"
    assert api.get(f"/api/v1/appointments/{appointment_id}", headers=headers).json()["transcript"] is None

    saved = api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "DOCUMENTATION_PENDING"
    assert saved.json()["generation_allowed"] is False
    deferred = api.post(f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers)
    assert deferred.status_code == 409
    assert deferred.json()["error"]["code"] == "generation_deferred_treatment_plan"

    assert sync_plan(
        api,
        headers,
        request_id="plans-renewed-1",
        external_id="PLAN-RENEWED",
        status="ACTIVE",
        effective_date="2026-07-01",
        expiration_date="2030-01-01",
        goal="Current plan goal",
        objective="Current plan objective",
        source_updated_at="2026-07-01T12:00:00Z",
    ).status_code == 200
    generated = api.post(f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers)
    assert generated.status_code == 200
    body = generated.json()
    assert body["bullet_points"] == bullets
    assert all(fact in body["note_content"] for fact in bullets)
    assert "PLAN-RENEWED" in body["note_content"]
    assert "Current plan goal" in body["note_content"]
    assert "Historical goal" not in body["note_content"]


def test_short_voice_transcript_is_rejected_without_storage(api, headers):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
        note_type="COUNSELOR",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    response = api.put(
        f"/api/v1/appointments/{appointment_id}/voice-summary",
        headers=headers,
        json={
            "duration_seconds": 299,
            "transcript": [
                {"speaker": "STAFF", "text": "A clinician-supplied question."},
                {"speaker": "CLIENT", "text": "A client-supplied answer."},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "recording_too_short"
    appointment = api.get(f"/api/v1/appointments/{appointment_id}", headers=headers).json()
    assert appointment["transcript"] is None
    assert appointment["documentation_method"] is None


def test_text_summary_requires_six_or_seven_unique_facts(api, headers):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    response = api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": ["one", "two", "three", "four", "five"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_failed"


def test_text_summary_preserves_source_bullets_byte_for_byte(api, headers):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    exact = [
        "- Original clinician prefix remains.",
        "  Leading spaces remain as entered.",
        "Trailing spaces remain.  ",
        "Punctuation: [brackets] / slash remains.",
        "Capitalization Is Preserved.",
        "Final source fact remains unchanged.",
    ]
    saved = api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": exact},
    )
    assert saved.status_code == 200
    assert saved.json()["bullet_points"] == exact


def test_cancelled_appointment_is_locked_against_restart(api, headers):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    cancelled = api.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["locked_at"]
    restart = api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    assert restart.status_code == 409
    assert restart.json()["error"]["code"] == "appointment_locked"


def test_changing_source_facts_invalidates_the_existing_draft(api, headers, bullets):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    generated = api.post(
        f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers
    )
    assert generated.status_code == 200
    assert generated.json()["note_content"]

    changed = [*bullets[:-1], "Client requested a follow-up in two weeks."]
    resaved = api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": changed},
    )
    assert resaved.status_code == 200
    assert resaved.json()["bullet_points"] == changed
    assert resaved.json()["note_content"] is None
    assert resaved.json()["generated_with_plan_external_id"] is None
    assert resaved.json()["reviewed_at"] is None
    assert resaved.json()["approved_at"] is None


def test_plan_change_after_generation_requires_regeneration(api, headers, bullets):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    draft = api.post(
        f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers
    ).json()["note_content"]
    finalized = draft.replace(
        "[Additional clinician documentation required; no supported fact was supplied.]",
        "Clinician reviewed this section and documented no additional supplied information.",
    )
    api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": finalized},
    )
    api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers)

    assert sync_plan(
        api,
        headers,
        request_id="plans-replacement-1",
        external_id="PLAN-REPLACEMENT",
        status="ACTIVE",
        effective_date="2026-07-01",
        expiration_date="2030-01-01",
        goal="Replacement goal",
        objective="Replacement objective",
        source_updated_at="2026-07-02T12:00:00Z",
    ).status_code == 200
    approval = api.post(
        f"/api/v1/appointments/{appointment_id}/approve", headers=headers
    )
    assert approval.status_code == 409
    assert approval.json()["error"]["code"] == "stale_generation_plan"

    regenerated = api.post(
        f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["generated_with_plan_external_id"] == "PLAN-REPLACEMENT"
    assert "Replacement goal" in regenerated.json()["note_content"]


def test_in_place_plan_update_invalidates_generated_snapshot(api, headers, bullets):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    draft = api.post(
        f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers
    ).json()["note_content"]
    finalized = draft.replace(
        "[Additional clinician documentation required; no supported fact was supplied.]",
        "Clinician reviewed this section and documented no additional supplied information.",
    )
    api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": finalized},
    )
    api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers)

    updated = sync_plan(
        api,
        headers,
        request_id="plans-active-update-1",
        external_id="PLAN-ACTIVE",
        status="ACTIVE",
        effective_date="2026-01-01",
        expiration_date="2030-01-01",
        goal="Updated goal on the same external plan",
        objective="Updated objective on the same external plan",
        source_updated_at="2026-08-01T12:00:00Z",
    )
    assert updated.status_code == 200
    assert updated.json()["updated"] == 1
    approval = api.post(
        f"/api/v1/appointments/{appointment_id}/approve", headers=headers
    )
    assert approval.status_code == 409
    assert approval.json()["error"]["code"] == "stale_generation_plan"


def test_heading_only_note_cannot_be_approved_or_completed(api, headers, bullets):
    seed_active(api, headers)
    created = create_appointment(
        api,
        headers,
        goal="Improve appointment participation",
        objective="Identify one transportation strategy",
        note_type="COUNSELOR",
    )
    appointment_id = created.json()["id"]
    api.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
    api.put(
        f"/api/v1/appointments/{appointment_id}/text-summary",
        headers=headers,
        json={"bullet_points": bullets},
    )
    api.post(f"/api/v1/appointments/{appointment_id}/generate-note", headers=headers)
    headings_only = """# Counselor Note

## Document Control
- Appointment date: 2026-04-15
- Service type: Synthetic service
- Staff member: test-clinician
- Source method: Clinician-entered bullet points
- Treatment plan: PLAN-ACTIVE

## Session Context
## Goals and Objectives Addressed
## Interventions
## Client Response
## Plan
"""
    edited = api.put(
        f"/api/v1/appointments/{appointment_id}/note",
        headers=headers,
        json={"content": headings_only},
    )
    assert edited.status_code == 200
    api.post(f"/api/v1/appointments/{appointment_id}/review", headers=headers)
    approval = api.post(
        f"/api/v1/appointments/{appointment_id}/approve", headers=headers
    )
    assert approval.status_code == 422
    errors = approval.json()["error"]["details"]["errors"]
    assert any(error.startswith("empty_section:") for error in errors)
    completion = api.post(
        f"/api/v1/appointments/{appointment_id}/complete", headers=headers
    )
    assert completion.status_code == 409
