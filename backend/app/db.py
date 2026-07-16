from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    given_name_enc TEXT NOT NULL,
    family_name_enc TEXT NOT NULL,
    date_of_birth_enc TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    source_updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treatment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'EXPIRED')),
    effective_date TEXT NOT NULL,
    expiration_date TEXT,
    goals_enc TEXT NOT NULL,
    objectives_enc TEXT NOT NULL,
    source_updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_plan_client_active
    ON treatment_plans(client_id, status, effective_date DESC, source_updated_at DESC);

CREATE TABLE IF NOT EXISTS sync_receipts (
    operation TEXT NOT NULL,
    request_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(operation, request_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    appointment_date TEXT NOT NULL,
    staff_member TEXT NOT NULL,
    service_type TEXT NOT NULL,
    note_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'SCHEDULED', 'IN_PROGRESS', 'DOCUMENTATION_PENDING', 'COMPLETED', 'CANCELLED'
    )),
    documentation_method TEXT CHECK (documentation_method IN ('TEXT', 'VOICE')),
    selected_goals_enc TEXT NOT NULL,
    selected_objectives_enc TEXT NOT NULL,
    bullet_points_enc TEXT,
    transcript_enc TEXT,
    transcript_duration_seconds INTEGER,
    plan_id_at_generation INTEGER REFERENCES treatment_plans(id),
    plan_snapshot_hash_at_generation TEXT,
    source_snapshot_hash_at_generation TEXT,
    note_content_enc TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    approved_at TEXT,
    approved_by TEXT,
    generated_at TEXT,
    completed_at TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id TEXT NOT NULL REFERENCES appointments(id),
    revision INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('GENERATED', 'EDITED')),
    content_enc TEXT NOT NULL,
    editor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(appointment_id, revision)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL UNIQUE
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cipher = Fernet(settings.data_key)
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            # Forward-only compatibility for local databases created by an older
            # reference build. Production deployments should use reviewed migrations.
            appointment_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(appointments)")
            }
            if "plan_snapshot_hash_at_generation" not in appointment_columns:
                connection.execute(
                    "ALTER TABLE appointments ADD COLUMN plan_snapshot_hash_at_generation TEXT"
                )
            if "source_snapshot_hash_at_generation" not in appointment_columns:
                connection.execute(
                    "ALTER TABLE appointments ADD COLUMN source_snapshot_hash_at_generation TEXT"
                )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.settings.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def encrypt_text(self, value: str) -> str:
        return self.cipher.encrypt(value.encode()).decode()

    def decrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Stored protected data could not be authenticated") from exc

    def encrypt_json(self, value: Any) -> str:
        return self.encrypt_text(json.dumps(value, sort_keys=True, separators=(",", ":")))

    def decrypt_json(self, value: str | None) -> Any:
        decrypted = self.decrypt_text(value)
        return None if decrypted is None else json.loads(decrypted)

    def audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str = "SUCCESS",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a PHI-free, HMAC-chained audit event."""
        occurred_at = utcnow()
        metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
        previous = connection.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["entry_hash"] if previous else "GENESIS"
        body = "|".join(
            (occurred_at, actor_id, action, resource_type, resource_id, outcome, metadata_json, previous_hash)
        )
        entry_hash = hmac.new(self.settings.audit_key, body.encode(), hashlib.sha256).hexdigest()
        connection.execute(
            """INSERT INTO audit_log
               (occurred_at, actor_id, action, resource_type, resource_id, outcome,
                metadata_json, previous_hash, entry_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                occurred_at,
                actor_id,
                action,
                resource_type,
                resource_id,
                outcome,
                metadata_json,
                previous_hash,
                entry_hash,
            ),
        )
