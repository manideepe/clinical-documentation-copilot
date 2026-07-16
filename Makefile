PYTHON ?= python3
BACKEND_PYTHON := backend/.venv/bin/python
BACKEND_PIP := backend/.venv/bin/pip
BACKEND_PYTEST := backend/.venv/bin/pytest

.PHONY: help setup setup-backend setup-frontend data data-validate test test-backend test-frontend lint build audit evidence run-api run-ui report verify clean-generated

help:
	@echo "setup           Install backend and frontend dependencies"
	@echo "data            Download, profile, and validate the Synthea benchmark"
	@echo "test            Run backend and frontend automated tests"
	@echo "lint             Run static checks"
	@echo "build            Build the browser application"
	@echo "audit            Check Python and Node dependencies for known vulnerabilities"
	@echo "evidence         Run tests, builds, audits, and performance evidence collection"
	@echo "run-api          Start the FastAPI service on 127.0.0.1:8000"
	@echo "run-ui           Start the Vite application on 127.0.0.1:5173"
	@echo "report           Regenerate and verify the 24-page research PDF"
	@echo "verify           Run release-oriented checks"

setup: setup-backend setup-frontend

setup-backend:
	$(PYTHON) -m venv backend/.venv
	$(BACKEND_PIP) install -r backend/requirements.txt -r backend/requirements-dev.txt

setup-frontend:
	cd frontend && npm ci

data:
	$(PYTHON) scripts/download_synthea.py
	$(PYTHON) scripts/profile_dataset.py
	$(PYTHON) scripts/validate_dataset.py

data-validate:
	$(PYTHON) scripts/profile_dataset.py
	$(PYTHON) scripts/validate_dataset.py

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && npm test -- --reporter=verbose

lint:
	cd backend && .venv/bin/python -m compileall -q app tests
	cd frontend && npm run lint

build:
	cd frontend && npm run build

audit:
	cd backend && .venv/bin/pip-audit -r requirements-dev.txt
	cd frontend && npm audit --audit-level=low

evidence:
	$(BACKEND_PYTHON) scripts/collect_test_evidence.py

run-api:
	cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

run-ui:
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

report:
	$(BACKEND_PYTHON) scripts/generate_report.py
	$(BACKEND_PYTHON) scripts/verify_report.py

verify: evidence data-validate report
	$(BACKEND_PYTHON) scripts/verify_repository.py

clean-generated:
	rm -rf frontend/dist frontend/coverage backend/htmlcov backend/.coverage tmp/pdfs/*
