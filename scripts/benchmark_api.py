#!/usr/bin/env python3
"""Run a deterministic local API latency smoke benchmark and save evidence."""

from __future__ import annotations

import json
import math
import platform
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(pct * len(ordered)) - 1)
    return ordered[index]


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "requests": len(values),
        "min_ms": round(min(values), 3),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "max_ms": round(max(values), 3),
    }


def timed(call: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    response = call()
    return response, (time.perf_counter() - started) * 1000


def main() -> int:
    headers = {
        "X-Internal-Auth": "local-development-gateway",
        "X-User-ID": "benchmark-user",
        "X-Role": "ADMINISTRATOR",
        "X-Session-Expires-At": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    failures: list[str] = []
    health_times: list[float] = []
    client_times: list[float] = []
    generation_times: list[float] = []

    with tempfile.TemporaryDirectory(prefix="clinical-copilot-benchmark-") as temp:
        app = create_app(Path(temp) / "benchmark.sqlite3")
        with TestClient(app) as client:
            synced = client.post(
                "/api/v1/ehr-sync/clients",
                headers=headers,
                json={
                    "request_id": "benchmark-client-0001",
                    "clients": [{
                        "external_id": "BENCH-C-001",
                        "given_name": "Synthetic",
                        "family_name": "Benchmark",
                        "date_of_birth": "1990-01-01",
                        "is_active": True,
                        "source_updated_at": "2026-01-01T00:00:00Z",
                    }],
                },
            )
            if synced.status_code != 200:
                failures.append(f"client seed returned {synced.status_code}")
            planned = client.post(
                "/api/v1/ehr-sync/treatment-plans",
                headers=headers,
                json={
                    "request_id": "benchmark-plan-0001",
                    "treatment_plans": [{
                        "external_id": "BENCH-PLAN-001",
                        "client_external_id": "BENCH-C-001",
                        "status": "ACTIVE",
                        "effective_date": "2026-01-01",
                        "expiration_date": "2030-01-01",
                        "goals": ["Benchmark goal"],
                        "objectives": ["Benchmark objective"],
                        "source_updated_at": "2026-01-02T00:00:00Z",
                    }],
                },
            )
            if planned.status_code != 200:
                failures.append(f"plan seed returned {planned.status_code}")

            for _ in range(250):
                response, elapsed = timed(lambda: client.get("/api/v1/health"))
                health_times.append(elapsed)
                if response.status_code != 200:
                    failures.append(f"health returned {response.status_code}")

            for _ in range(100):
                response, elapsed = timed(
                    lambda: client.get("/api/v1/clients", headers=headers)
                )
                client_times.append(elapsed)
                if response.status_code != 200:
                    failures.append(f"client list returned {response.status_code}")

            facts = [
                "Clinician reviewed the synthetic schedule.",
                "Client identified a synthetic transportation barrier.",
                "Clinician supplied the synthetic clinic telephone number.",
                "Client reported attending a synthetic community program.",
                "The treatment goal was discussed in the synthetic session.",
                "Client requested a synthetic follow-up next week.",
            ]
            for index in range(50):
                created = client.post(
                    "/api/v1/appointments",
                    headers=headers,
                    json={
                        "client_external_id": "BENCH-C-001",
                        "appointment_date": f"2026-07-{(index % 20) + 1:02d}T14:00:00-05:00",
                        "staff_member": "benchmark-clinician",
                        "service_type": "Synthetic benchmark service",
                        "note_type": "CASE_MANAGEMENT",
                        "treatment_goals": ["Benchmark goal"],
                        "treatment_objectives": ["Benchmark objective"],
                    },
                )
                if created.status_code != 201:
                    failures.append(f"appointment create returned {created.status_code}")
                    continue
                appointment_id = created.json()["id"]
                client.post(f"/api/v1/appointments/{appointment_id}/start", headers=headers)
                client.put(
                    f"/api/v1/appointments/{appointment_id}/text-summary",
                    headers=headers,
                    json={"bullet_points": facts},
                )
                response, elapsed = timed(
                    lambda appointment_id=appointment_id: client.post(
                        f"/api/v1/appointments/{appointment_id}/generate-note",
                        headers=headers,
                    )
                )
                generation_times.append(elapsed)
                if response.status_code != 200:
                    failures.append(f"generation returned {response.status_code}")

    metrics = {
        "health": summary(health_times),
        "client_list_encrypted_fields": summary(client_times),
        "deterministic_note_generation": summary(generation_times),
    }
    thresholds_ms = {"health_p95": 25.0, "client_list_p95": 50.0, "generation_p95": 100.0}
    passed = (
        not failures
        and metrics["health"]["p95_ms"] <= thresholds_ms["health_p95"]
        and metrics["client_list_encrypted_fields"]["p95_ms"] <= thresholds_ms["client_list_p95"]
        and metrics["deterministic_note_generation"]["p95_ms"] <= thresholds_ms["generation_p95"]
    )
    result = {
        "benchmark": "local in-process API smoke benchmark",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "scope_warning": "Local TestClient latency is regression evidence, not capacity or production-load certification.",
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "thresholds_ms": thresholds_ms,
        "metrics": metrics,
        "failures": failures[:20],
    }
    destination = ROOT / "evidence" / "tests" / "performance_results.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
