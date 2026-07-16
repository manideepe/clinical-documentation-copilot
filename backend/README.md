# Clinical Documentation Copilot — backend

This folder contains a locally runnable FastAPI reference service for a treatment-plan-aware EHR documentation extension. It is intentionally deterministic and uses no external AI service: the local generator formats only supplied appointment facts and the latest active treatment plan. Missing clinical information is marked for a clinician instead of guessed.

The implementation is production-shaped, but it is not a production deployment and does **not** claim HIPAA compliance. Compliance depends on the full technical and administrative environment, risk analysis, contracts, policies, operations, identity system, infrastructure, and validation. See [Security boundary](#security-boundary).

## Implemented workflows

- Idempotent EHR client synchronization keyed by unique external client ID and request ID.
- Idempotent treatment-plan synchronization with source-update ordering.
- Selection of only the newest currently effective `ACTIVE` plan. Older, inactive, future, and expired plans are excluded from generation.
- Appointment states: `SCHEDULED`, `IN_PROGRESS`, `DOCUMENTATION_PENDING`, `COMPLETED`, and `CANCELLED`.
- Six-to-seven-fact text summaries and a diarized transcript adapter with `STAFF` and `CLIENT` turns.
- Hard expired-plan gate: appointments and text-fact saving remain available; voice ingestion and generation return explicit errors; no voice payload is stored.
- Deferred generation after a renewed plan is synchronized, using the unchanged saved facts and the new active plan.
- Eight note contracts, each with its own headings, required-field metadata, style, grounding policy, and structural validation.
- Clinician editing, review, approval, completion, immutable completion lock, and append-only note revisions.
- Role-permission scaffolding, expiring gateway sessions, encrypted clinical fields, security response headers, and HMAC-chained PHI-free audit events.

## Quick start

Python 3.11 or later is required.

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API documentation is available at `http://127.0.0.1:8000/api/docs` in non-production mode. The health endpoint is unauthenticated and contains no clinical data:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

All clinical endpoints expect identity assertions from an authentication gateway:

```text
X-Internal-Auth: local-development-gateway
X-User-ID: local-admin
X-Role: ADMINISTRATOR
X-Session-Expires-At: 2030-01-01T00:00:00Z
```

The default token and keys are for local development only.

## Configuration

| Environment variable | Development default | Purpose |
|---|---|---|
| `EHR_ENVIRONMENT` | `development` | Set to `production` to disable interactive API docs. |
| `EHR_DATABASE_PATH` | `./var/clinical_copilot.sqlite3` | SQLite database path. |
| `EHR_DATA_KEY` | insecure local value | High-entropy secret used to derive the field-encryption key. |
| `EHR_AUDIT_KEY` | insecure local value | Separate high-entropy HMAC key for the audit chain. |
| `EHR_GATEWAY_TOKEN` | insecure local value | Shared assertion between this service and a trusted identity gateway. |
| `EHR_CORS_ORIGINS` | local Vite origins | Explicit comma-separated browser origins; wildcard is rejected in production. |
| `EHR_MAX_REQUEST_BYTES` | `8388608` | Content-Length limit; a production proxy must also bound streamed/chunked bodies. |

For any non-local environment, inject independent random secrets from a managed secret store, restrict database file permissions, terminate TLS at a trusted reverse proxy, and prevent clients from setting or forwarding identity headers directly.

## API outline

| Method and path | Purpose | Key permission |
|---|---|---|
| `POST /api/v1/ehr-sync/clients` | Idempotently upsert clients | `SYNC_EHR` |
| `POST /api/v1/ehr-sync/treatment-plans` | Idempotently upsert plans | `SYNC_EHR` |
| `GET /api/v1/clients` | List synchronized clients and current/latest plans | `VIEW_CLIENTS` |
| `GET /api/v1/note-types` | List eight note contracts | `VIEW_CLIENTS` |
| `POST /api/v1/appointments` | Create a scheduled appointment | `GENERATE_NOTES` |
| `POST /api/v1/appointments/{id}/start` | Start a scheduled appointment | `GENERATE_NOTES` |
| `POST /api/v1/appointments/{id}/cancel` | Cancel and lock an appointment | `COMPLETE_APPOINTMENTS` |
| `PUT /api/v1/appointments/{id}/text-summary` | Save six or seven supplied facts | `GENERATE_NOTES` |
| `PUT /api/v1/appointments/{id}/voice-summary` | Save a 5+ minute diarized transcript; never audio | `ACCESS_VOICE` |
| `POST /api/v1/appointments/{id}/generate-note` | Create a deterministic grounded draft | `GENERATE_NOTES` |
| `PUT /api/v1/appointments/{id}/note` | Edit all note content and create a revision | `EDIT_NOTES` |
| `POST /api/v1/appointments/{id}/review` | Record clinician review | `EDIT_NOTES` |
| `POST /api/v1/appointments/{id}/approve` | Validate and approve the note | `EDIT_NOTES` |
| `POST /api/v1/appointments/{id}/complete` | Complete and lock the appointment | `COMPLETE_APPOINTMENTS` |
| `GET /api/v1/appointments/{id}/revisions` | Retrieve preserved note history | `EDIT_NOTES` |
| `GET /api/v1/audit-events` | Retrieve audit evidence | `VIEW_AUDIT` |

The OpenAPI document at `/openapi.json` is the authoritative request/response contract.

## Grounding and clinical safety

The generator in `app/generator.py` is a transparent offline baseline. It can add fixed labels and template structure, but every clinical proposition is copied from one of these sources:

1. appointment metadata;
2. the latest currently effective active plan; and
3. clinician-entered bullet points or diarized transcript turns.

It does not infer diagnosis, risk, examination findings, interventions, symptoms, quotations, progress, or outcomes. Template sections without supported data receive an explicit missing-information marker. Approval fails until a clinician edits those markers, and editing clears prior review. Completion requires a generated, structurally valid, reviewed, and approved note. Completion and cancellation set an immutable lock.

The transcript endpoint is an adapter boundary for a future locally operated speech/diarization component. It accepts text turns and duration metadata only. This repository intentionally has no audio upload or audio persistence route. If the current plan is expired, missing, inactive, or future-dated, the adapter rejects the request before storage. Recordings shorter than 300 seconds are also rejected before storage.

## Latest-plan and deferred-generation rules

Plan eligibility is evaluated at read and generation time:

```text
status = ACTIVE
effective_date <= today
expiration_date is absent OR expiration_date >= today
```

Eligible rows are ordered by effective date, source update time, and local ID, newest first. When no plan is eligible, text facts can still be saved and the appointment becomes `DOCUMENTATION_PENDING`, but generation returns `generation_deferred_treatment_plan`. Synchronizing a new eligible plan makes generation available immediately. The generator reads the new plan and never mutates the saved facts.

`request_id` plus a canonical request hash protects both sync endpoints against retries. An exact replay returns the prior result; reuse of a request ID with a changed payload returns `409 idempotency_conflict`. External client and plan IDs have database uniqueness constraints as an additional control. Stale source updates do not overwrite newer records.

## Security boundary

Safeguards demonstrated here include:

- Fernet authenticated encryption for names, date of birth, treatment content, supplied facts, transcript text, and note/revision content;
- separate configuration secrets for protected data and audit integrity;
- role-to-permission authorization and explicit session expiry;
- no-store, anti-framing, MIME-sniffing, referrer, and restrictive content-security headers;
- parameterized SQLite access, foreign keys, constraints, and transactional sync batches;
- append-only audit events chained with HMAC and designed to exclude PHI from metadata;
- no external inference call, training call, telemetry integration, or public-model data transfer.

Important production work remains: a real OIDC/SMART-on-FHIR identity integration; per-client/team authorization; TLS and certificate policy; encrypted volumes or an encrypted managed database for identifiers and metadata that remain queryable; secret rotation; centralized immutable audit export and monitoring; backup/restore controls; vulnerability management; retention/deletion rules; consent and audio policy; incident response; accessibility and usability validation; clinical safety validation; and organizational privacy/security review.

The API trusts identity headers only after checking `X-Internal-Auth`. A production proxy must strip incoming identity headers and set new verified values. The built-in shared-token assertion is scaffolding, not a complete authentication system.

## Tests

Run the complete backend suite:

```bash
.venv/bin/python -m pytest
```

The suite uses an isolated temporary SQLite database per test and covers:

- health and response-security headers;
- missing/expired sessions and role denial;
- exact sync replay, changed-payload idempotency conflict, and unique client behavior;
- newest-active-plan selection;
- the complete grounded text workflow;
- required clinician remediation of missing-data markers;
- review invalidation on edit, approval ordering, completion, locking, and revision history;
- expired-plan voice rejection with no transcript persistence;
- deferred text generation followed by plan renewal and generation from unchanged facts;
- five-minute voice minimum with no storage after rejection;
- six-to-seven unique text-fact validation;
- cancellation locking; and
- all eight template contracts.

Tests are deterministic, free to run, and require no network or external service after dependencies are installed.

## Project layout

```text
backend/
├── app/
│   ├── config.py       # environment configuration
│   ├── db.py           # SQLite schema, encryption, audit chain
│   ├── generator.py    # deterministic grounded formatting
│   ├── main.py         # FastAPI routes and error handling
│   ├── schemas.py      # validated API contracts
│   ├── security.py     # roles, permissions, session assertions
│   ├── service.py      # workflow and safety rules
│   └── templates.py    # eight note definitions and validation
├── tests/              # API and safety workflow tests
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```
