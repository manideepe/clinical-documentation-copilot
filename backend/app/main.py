from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import Repository
from .schemas import (
    AppointmentCreate,
    AppointmentView,
    ClientSyncRequest,
    NoteEdit,
    TextSummarySave,
    TreatmentPlanSyncRequest,
    VoiceSummarySave,
)
from .security import CurrentUser, Permission, require
from .service import ClinicalService, DomainError
from .templates import TEMPLATES


def _service(request: Request) -> ClinicalService:
    return request.app.state.service


def create_app(database_path: str | Path | None = None) -> FastAPI:
    settings = Settings.from_env(database_path)
    repository = Repository(settings)
    app = FastAPI(
        title="Clinical Documentation Copilot API",
        version="1.0.0",
        description=(
            "Deterministic, treatment-plan-aware clinical documentation workflow. "
            "Generated content always requires clinician review and approval."
        ),
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.service = ClinicalService(repository)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "X-Internal-Auth",
            "X-Request-ID",
            "X-Role",
            "X-Session-Expires-At",
            "X-User-ID",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_size_limit(request: Request, call_next):
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "invalid_content_length",
                            "message": "Content-Length must be an integer",
                        }
                    },
                )
            if declared_bytes > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "request_too_large",
                            "message": "Request body exceeds the configured limit",
                        }
                    },
                )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        error = {"code": exc.code, "message": exc.message}
        if exc.details:
            error["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_failed",
                    "message": "Request data did not satisfy the API contract",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    @app.get("/api/v1/health", tags=["operations"])
    def health() -> dict:
        return {
            "status": "ok",
            "generation_mode": "deterministic_local",
            "audio_storage": "not_implemented",
        }

    @app.get("/api/v1/note-types", tags=["templates"])
    def note_types(
        _: CurrentUser = Depends(require(Permission.VIEW_CLIENTS)),
    ) -> dict:
        return {"items": [template.public() for template in TEMPLATES.values()]}

    @app.post("/api/v1/ehr-sync/clients", tags=["ehr-sync"])
    def sync_clients(
        payload: ClientSyncRequest,
        request: Request,
        user: CurrentUser = Depends(require(Permission.SYNC_EHR)),
    ) -> dict:
        return _service(request).sync_clients(payload, user.user_id)

    @app.post("/api/v1/ehr-sync/treatment-plans", tags=["ehr-sync"])
    def sync_treatment_plans(
        payload: TreatmentPlanSyncRequest,
        request: Request,
        user: CurrentUser = Depends(require(Permission.SYNC_EHR)),
    ) -> dict:
        return _service(request).sync_plans(payload, user.user_id)

    @app.get("/api/v1/clients", tags=["clients"])
    def list_clients(
        request: Request,
        _: CurrentUser = Depends(require(Permission.VIEW_CLIENTS)),
    ) -> dict:
        return {"items": _service(request).list_clients()}

    @app.post(
        "/api/v1/appointments",
        tags=["appointments"],
        response_model=AppointmentView,
        status_code=201,
    )
    def create_appointment(
        payload: AppointmentCreate,
        request: Request,
        user: CurrentUser = Depends(require(Permission.GENERATE_NOTES)),
    ) -> dict:
        return _service(request).create_appointment(payload, user.user_id)

    @app.get(
        "/api/v1/appointments/{appointment_id}",
        tags=["appointments"],
        response_model=AppointmentView,
    )
    def get_appointment(
        appointment_id: str,
        request: Request,
        _: CurrentUser = Depends(require(Permission.VIEW_CLIENTS)),
    ) -> dict:
        return _service(request).get_appointment(appointment_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/start",
        tags=["appointments"],
        response_model=AppointmentView,
    )
    def start_appointment(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.GENERATE_NOTES)),
    ) -> dict:
        return _service(request).start_appointment(appointment_id, user.user_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/cancel",
        tags=["appointments"],
        response_model=AppointmentView,
    )
    def cancel_appointment(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.COMPLETE_APPOINTMENTS)),
    ) -> dict:
        return _service(request).cancel_appointment(appointment_id, user.user_id)

    @app.put(
        "/api/v1/appointments/{appointment_id}/text-summary",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def save_text_summary(
        appointment_id: str,
        payload: TextSummarySave,
        request: Request,
        user: CurrentUser = Depends(require(Permission.GENERATE_NOTES)),
    ) -> dict:
        return _service(request).save_text_summary(appointment_id, payload, user.user_id)

    @app.put(
        "/api/v1/appointments/{appointment_id}/voice-summary",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def save_voice_summary(
        appointment_id: str,
        payload: VoiceSummarySave,
        request: Request,
        user: CurrentUser = Depends(require(Permission.ACCESS_VOICE)),
    ) -> dict:
        return _service(request).save_voice_summary(appointment_id, payload, user.user_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/generate-note",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def generate_note(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.GENERATE_NOTES)),
    ) -> dict:
        return _service(request).generate_note(appointment_id, user.user_id)

    @app.put(
        "/api/v1/appointments/{appointment_id}/note",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def edit_note(
        appointment_id: str,
        payload: NoteEdit,
        request: Request,
        user: CurrentUser = Depends(require(Permission.EDIT_NOTES)),
    ) -> dict:
        return _service(request).edit_note(appointment_id, payload.content, user.user_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/review",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def mark_reviewed(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.EDIT_NOTES)),
    ) -> dict:
        return _service(request).mark_reviewed(appointment_id, user.user_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/approve",
        tags=["documentation"],
        response_model=AppointmentView,
    )
    def approve_note(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.EDIT_NOTES)),
    ) -> dict:
        return _service(request).approve_note(appointment_id, user.user_id)

    @app.post(
        "/api/v1/appointments/{appointment_id}/complete",
        tags=["appointments"],
        response_model=AppointmentView,
    )
    def complete_appointment(
        appointment_id: str,
        request: Request,
        user: CurrentUser = Depends(require(Permission.COMPLETE_APPOINTMENTS)),
    ) -> dict:
        return _service(request).complete_appointment(appointment_id, user.user_id)

    @app.get("/api/v1/appointments/{appointment_id}/revisions", tags=["documentation"])
    def note_revisions(
        appointment_id: str,
        request: Request,
        _: CurrentUser = Depends(require(Permission.EDIT_NOTES)),
    ) -> dict:
        return {"items": _service(request).revisions(appointment_id)}

    @app.get("/api/v1/audit-events", tags=["security"])
    def audit_events(
        request: Request,
        limit: int = Query(default=100, ge=1, le=1000),
        _: CurrentUser = Depends(require(Permission.VIEW_AUDIT)),
    ) -> dict:
        return {"items": _service(request).audit_events(limit)}

    return app


app = create_app()
