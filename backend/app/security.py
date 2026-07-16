from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status


class Role(StrEnum):
    ADMINISTRATOR = "ADMINISTRATOR"
    CLINICAL_SUPERVISOR = "CLINICAL_SUPERVISOR"
    COUNSELOR = "COUNSELOR"
    NURSE = "NURSE"
    CASE_MANAGER = "CASE_MANAGER"
    MEDICAL_PROVIDER = "MEDICAL_PROVIDER"


class Permission(StrEnum):
    SYNC_EHR = "SYNC_EHR"
    VIEW_CLIENTS = "VIEW_CLIENTS"
    GENERATE_NOTES = "GENERATE_NOTES"
    EDIT_NOTES = "EDIT_NOTES"
    COMPLETE_APPOINTMENTS = "COMPLETE_APPOINTMENTS"
    ACCESS_VOICE = "ACCESS_VOICE"
    MANAGE_TEMPLATES = "MANAGE_TEMPLATES"
    VIEW_AUDIT = "VIEW_AUDIT"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMINISTRATOR: set(Permission),
    Role.CLINICAL_SUPERVISOR: {
        Permission.SYNC_EHR,
        Permission.VIEW_CLIENTS,
        Permission.GENERATE_NOTES,
        Permission.EDIT_NOTES,
        Permission.COMPLETE_APPOINTMENTS,
        Permission.ACCESS_VOICE,
        Permission.MANAGE_TEMPLATES,
        Permission.VIEW_AUDIT,
    },
    Role.COUNSELOR: {
        Permission.VIEW_CLIENTS,
        Permission.GENERATE_NOTES,
        Permission.EDIT_NOTES,
        Permission.COMPLETE_APPOINTMENTS,
        Permission.ACCESS_VOICE,
    },
    Role.NURSE: {
        Permission.VIEW_CLIENTS,
        Permission.GENERATE_NOTES,
        Permission.EDIT_NOTES,
        Permission.COMPLETE_APPOINTMENTS,
        Permission.ACCESS_VOICE,
    },
    Role.CASE_MANAGER: {
        Permission.VIEW_CLIENTS,
        Permission.GENERATE_NOTES,
        Permission.EDIT_NOTES,
        Permission.COMPLETE_APPOINTMENTS,
        Permission.ACCESS_VOICE,
    },
    Role.MEDICAL_PROVIDER: {
        Permission.VIEW_CLIENTS,
        Permission.GENERATE_NOTES,
        Permission.EDIT_NOTES,
        Permission.COMPLETE_APPOINTMENTS,
        Permission.ACCESS_VOICE,
    },
}


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: Role


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": code, "message": message})


def current_user(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_internal_auth: str | None = Header(default=None),
    x_session_expires_at: str | None = Header(default=None),
) -> CurrentUser:
    """Validate identity assertions from a trusted authentication gateway.

    This is deliberately gateway-oriented scaffolding, not an identity provider.
    Production must terminate TLS, authenticate users, and overwrite these headers.
    """
    expected = request.app.state.settings.gateway_token
    if not x_internal_auth or not hmac.compare_digest(x_internal_auth, expected):
        raise _unauthorized("invalid_gateway_assertion", "Authentication gateway assertion is missing or invalid")
    if not x_user_id or not x_role or not x_session_expires_at:
        raise _unauthorized("missing_identity", "Identity, role, and session expiry are required")
    try:
        role = Role(x_role)
    except ValueError as exc:
        raise _unauthorized("invalid_role", "The asserted role is not supported") from exc
    try:
        expires_at = datetime.fromisoformat(x_session_expires_at.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise _unauthorized("invalid_session_expiry", "Session expiry must be an ISO-8601 timestamp") from exc
    if expires_at.astimezone(UTC) <= datetime.now(UTC):
        raise _unauthorized("session_expired", "The authenticated session has expired")
    return CurrentUser(x_user_id, role)


def require(permission: Permission) -> Callable[[CurrentUser], CurrentUser]:
    def authorize(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if permission not in ROLE_PERMISSIONS[user.role]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {"code": "permission_denied", "message": f"{permission.value} permission is required"},
            )
        return user

    return authorize
