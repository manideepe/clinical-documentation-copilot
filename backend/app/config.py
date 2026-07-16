from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    Development defaults make the demonstration runnable without paid services.
    Deployments must provide unique secrets through the environment.
    """

    database_path: Path
    data_key: bytes
    gateway_token: str
    audit_key: bytes
    environment: str = "development"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    max_request_bytes: int = 8 * 1024 * 1024

    @classmethod
    def from_env(cls, database_path: str | Path | None = None) -> "Settings":
        environment = os.getenv("EHR_ENVIRONMENT", "development")
        db_path = Path(
            database_path
            or os.getenv("EHR_DATABASE_PATH", "./var/clinical_copilot.sqlite3")
        )
        raw_data_key = os.getenv("EHR_DATA_KEY", "local-development-data-key")
        # Fernet requires a URL-safe, 32-byte base64 key. Deriving it allows a
        # secret manager to supply an ordinary high-entropy passphrase.
        data_key = base64.urlsafe_b64encode(hashlib.sha256(raw_data_key.encode()).digest())
        gateway_token = os.getenv("EHR_GATEWAY_TOKEN", "local-development-gateway")
        raw_audit_key = os.getenv("EHR_AUDIT_KEY", "local-development-audit-key")
        if environment == "production":
            production_secrets = {
                "EHR_DATA_KEY": os.getenv("EHR_DATA_KEY"),
                "EHR_AUDIT_KEY": os.getenv("EHR_AUDIT_KEY"),
                "EHR_GATEWAY_TOKEN": os.getenv("EHR_GATEWAY_TOKEN"),
            }
            weak = [name for name, value in production_secrets.items() if not value or len(value) < 32]
            if weak:
                raise ValueError(
                    "Production requires independent secrets of at least 32 characters: "
                    + ", ".join(sorted(weak))
                )
            if len(set(production_secrets.values())) != len(production_secrets):
                raise ValueError("Production data, audit, and gateway secrets must be independent")
        audit_key = hashlib.sha256(raw_audit_key.encode()).digest()
        cors_origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "EHR_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
            ).split(",")
            if origin.strip()
        )
        if environment == "production" and "*" in cors_origins:
            raise ValueError("Wildcard CORS origins are not permitted in production")
        max_request_bytes = int(os.getenv("EHR_MAX_REQUEST_BYTES", str(8 * 1024 * 1024)))
        if max_request_bytes < 1024:
            raise ValueError("EHR_MAX_REQUEST_BYTES must be at least 1024")
        return cls(
            db_path,
            data_key,
            gateway_token,
            audit_key,
            environment,
            cors_origins,
            max_request_bytes,
        )
