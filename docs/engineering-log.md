# Threat Defense Swarm — Engineering & Debugging Log

This document records technical decisions, milestones, real issues encountered, root cause analyses, solutions, and empirical verification results throughout the development of the Threat Defense Swarm microservices.

---

## Milestone 1: Repository & Virtual Environment Bootstrap
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Initialized local Git repository, created isolated Python virtual environment (`.venv`), defined project dependencies in `pyproject.toml` and `requirements.txt`, created `.env.example` and `.env` configuration templates, and configured `.gitignore`.

### Engineering Notes & Verification
- Python Version: 3.14.6
- Virtual Environment: Created at `.venv`
- Dependency Installation: FastAPI, Pydantic, httpx, OpenAI, Pytest installed successfully into virtual environment.
- Git Repository: Initialized locally (`git init`).

---

## Milestone 2: Shared Contracts, Schemas, & Utilities
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Built `shared/` package containing versioned A2A envelope protocol (`A2AEnvelope`), compressed lean context (`A2AContext`), event models (`RawStreamItem`, `IntentClassification`, `TerminalResult`), tool response schemas (`IPReputationResponse`, `GeoLookupResponse`), structured JSON log formatter (`JSONFormatter`), configuration management (`shared/config.py`), and resilience mechanisms (`IdempotencyCache`, `execute_with_retry`).

### Engineering Notes & Verification
- Schema Validation: Pydantic v2 schemas for all payloads with strict bounds and field validation.
- Unit Testing: `tests/unit/test_shared.py` passed (A2A envelope serialization, FIFO idempotency eviction, exponential backoff retries).
- Test Results: 4 passing tests in 0.38s.

---

## Milestone 3: Service 1 — Triage Agent & Prompt Injection Defense
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Built Service 1 (Triage Agent) featuring input sanitization (`sanitizer.py`), prompt injection boundary guards (`<data>` tag framing), intent classification engine (`classifier.py`) supporting OpenAI structured outputs with fallback mock driver, context compression producing lean `A2AContext` objects, and `/ingest` & `/a2a/clarify` REST endpoints.

### Engineering Notes & Verification
- Injection Defense: Tested against multiple adversarial prompt injection variants (e.g., "ignore previous instructions", "system compromised", "disregard prior rules").
- Intent Classification: Filtered benign noise items to produce immediate terminal results vs routing threat events to context compression.
- Test Suite: `services/triage/tests/test_triage.py` passed cleanly (7 total suite tests passing in 0.91s).
