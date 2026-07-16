#!/usr/bin/env python3
"""Execute release checks and write a complete machine-readable evidence record."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "tests"
LOGS = EVIDENCE / "logs"


def run(name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    started = datetime.now(UTC)
    started_clock = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - started_clock
    combined = completed.stdout + ("\n" if completed.stdout and completed.stderr else "") + completed.stderr
    sanitized_output = combined.replace(str(ROOT), "$PROJECT_ROOT")
    sanitized_command = [part.replace(str(ROOT), "$PROJECT_ROOT") for part in command]
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{name}.log").write_text(sanitized_output, encoding="utf-8")
    return {
        "name": name,
        "command": sanitized_command,
        "cwd": cwd.relative_to(ROOT).as_posix() or ".",
        "started_at_utc": started.isoformat(),
        "duration_seconds": round(elapsed, 3),
        "exit_code": completed.returncode,
        "output": sanitized_output,
    }


def record(identifier: str, name: str, layer: str, status: str, description: str, run_name: str) -> dict[str, str]:
    return {
        "id": identifier,
        "name": name,
        "layer": layer,
        "status": status,
        "description": description,
        "run": run_name,
    }


def backend_records(result: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(r"^(tests/[^\s]+::test_[^\s]+)\s+(PASSED|FAILED|SKIPPED|XFAIL|XPASS|ERROR)", re.MULTILINE)
    for nodeid, outcome in pattern.findall(result["output"]):
        items.append(record(nodeid, nodeid.rsplit("::", 1)[-1], "backend", outcome.lower(), "FastAPI/domain workflow test", result["name"]))
    return items


def frontend_records(result: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(r"^[\s]*(?:✓|×|x)\s+(.+?)\s+>\s+(.+?)(?:\s+\d+ms)?$", re.MULTILINE)
    for index, (file_name, test_name) in enumerate(pattern.findall(result["output"]), start=1):
        line = next((line for line in result["output"].splitlines() if test_name in line and ">" in line), "")
        status = "passed" if "✓" in line else "failed"
        items.append(record(f"frontend-{index:03d}", test_name.strip(), "frontend", status, f"Vitest UI workflow test in {file_name.strip()}", result["name"]))
    return items


def main() -> int:
    backend_python = ROOT / "backend" / ".venv" / "bin" / "python"
    backend_pytest = [str(backend_python), "-m", "pytest", "-vv", "--tb=short"]
    checks = [
        run("backend_pytest", backend_pytest, ROOT / "backend"),
        run("backend_compile", [str(backend_python), "-m", "compileall", "-q", "app", "tests"], ROOT / "backend"),
        run("frontend_vitest", ["npm", "test", "--", "--reporter=verbose"], ROOT / "frontend"),
        run("frontend_lint", ["npm", "run", "lint"], ROOT / "frontend"),
        run("frontend_build", ["npm", "run", "build"], ROOT / "frontend"),
        run("python_dependency_audit", [str(ROOT / "backend" / ".venv" / "bin" / "pip-audit"), "-r", "requirements-dev.txt"], ROOT / "backend"),
        run("node_dependency_audit", ["npm", "audit", "--audit-level=low"], ROOT / "frontend"),
        run("api_performance", [str(backend_python), str(ROOT / "scripts" / "benchmark_api.py")], ROOT),
    ]

    tests = backend_records(checks[0]) + frontend_records(checks[2])
    for result in checks[1:2] + checks[3:]:
        status = "passed" if result["exit_code"] == 0 else "failed"
        tests.append(
            record(
                f"gate-{result['name']}",
                result["name"].replace("_", " ").title(),
                "release-gate",
                status,
                f"Command completed with exit code {result['exit_code']} in {result['duration_seconds']} seconds",
                result["name"],
            )
        )

    expected_backend = 23
    expected_frontend = 7
    discovery_errors: list[str] = []
    if len([item for item in tests if item["layer"] == "backend"]) != expected_backend:
        discovery_errors.append("Backend result parsing did not reconcile to 23 tests")
    if len([item for item in tests if item["layer"] == "frontend"]) != expected_frontend:
        discovery_errors.append("Frontend result parsing did not reconcile to 7 tests")

    failed_checks = [result["name"] for result in checks if result["exit_code"] != 0]
    failed_records = [item["id"] for item in tests if item["status"] not in {"passed"}]
    passed = not failed_checks and not failed_records and not discovery_errors
    generated_at = datetime.now(UTC).isoformat()
    inventory = {
        "schema_version": "1.0",
        "generated_at_utc": generated_at,
        "passed": passed,
        "environment": {
            "python": platform.python_version(),
            "node": subprocess.run(["node", "--version"], text=True, capture_output=True, check=False).stdout.strip(),
            "npm": subprocess.run(["npm", "--version"], text=True, capture_output=True, check=False).stdout.strip(),
            "platform": platform.platform(),
        },
        "summary": {
            "total_records": len(tests),
            "backend_tests": len([item for item in tests if item["layer"] == "backend"]),
            "frontend_tests": len([item for item in tests if item["layer"] == "frontend"]),
            "release_gates": len([item for item in tests if item["layer"] == "release-gate"]),
            "failed_checks": failed_checks,
            "failed_records": failed_records,
            "discovery_errors": discovery_errors,
        },
        "runs": [
            {key: value for key, value in result.items() if key != "output"}
            for result in checks
        ],
        "tests": tests,
    }
    summary = {
        "generated_at_utc": generated_at,
        "passed": passed,
        "commands_run": len(checks),
        **inventory["summary"],
        "logs": "evidence/tests/logs",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "test_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "test_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
