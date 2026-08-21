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

---

## Milestone 4: Service 2 — Resolution Agent & Mock Tools
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Built Service 2 (Resolution Agent) with mock security tools (`mock_tools.py` for IP reputation, Geo lookup, and Auth frequency), evidence sufficiency decision stage (`investigator.py`), final verdict rendering, bounded clarification loop handler (`clarification.py`), idempotency caching, and REST endpoints.

### Engineering Notes & Verification
- Mock Security Tools: Local deterministic database for IP reputation (`203.0.113.7` -> malicious), Geo lookup, and Auth frequency.
- Verdict Reasoning: Rendered structured verdicts (`block_ip`, `quarantine`, `monitor`, `allow`, `insufficient_context`) with confidence scores.
- Test Suite: `services/resolution/tests/test_resolution.py` passed cleanly (10 total suite tests passing in 1.05s).

---

## Milestone 5: A2A Communication Protocol & Bounded Clarification Loop
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Implemented inter-service A2A communication flow and bounded clarification loop negotiation. Created `shared/utilities/http.py` for client transport management.

### Real Engineering Issue & Fix Recorded
- **Problem Encountered**: During integration testing, clarification loop calls to Triage `/a2a/clarify` caused `httpx` timeouts when services were tested in-process without an active HTTP listener on port 8001.
- **Root Cause**: Hardcoded `httpx.AsyncClient` attempted TCP connection to port 8001, timing out when no server process was listening.
- **Solution & Why Chosen**: Introduced `shared/utilities/http.py` with `set_override_clients` to allow mounting `ASGITransport(app=triage_app)` during in-process testing while maintaining real HTTP capability when running under Uvicorn/Docker.
- **Tests Proving Fix**: `tests/integration/test_a2a_clarification.py` verified both threat processing and bounded clarification termination (exactly 2 attempts yielding `INSUFFICIENT_CONTEXT`). 12 total suite tests passing.

---

## Milestone 6: Bounded Investigation Loop & Transient Failure Recovery
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Verified that Resolution Agent investigation loop is strictly bounded at `<= 3` iterations and tested transient HTTP 503 retry recovery.

### Engineering Notes & Verification
- Loop Bound Verification: Confirmed investigation loop terminates after at most 3 iterations.
- Tool Failure Recovery: Tested mock tool HTTP 503 failures with exponential backoff retries. When retry budget was exhausted, `tool_503_exhausted` was logged in telemetry and system rendered final verdict based on remaining evidence without crashing.
- Test Suite: `tests/integration/test_investigation_resilience.py` passed cleanly. 14 total suite tests passing.

---

## Milestone 7: Service 3 — Saboteur / Chaos Injector
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Built Service 3 (Saboteur / Chaos Injector) as an independent asynchronous service supporting seedable random number generation (`ChaosInjector`), prompt injection poisoning, A2A packet drops, forced tool 503 errors, and REST control endpoints (`/chaos/config`, `/chaos/reset-seed`).

### Engineering Notes & Verification
- Seed Reproducibility: Confirmed 100% deterministic reproducibility when seeded (`ChaosInjector(seed=12345)`).
- Test Suite: `services/saboteur/tests/test_saboteur.py` passed cleanly. 17 total suite tests passing.

---

## Milestone 8: Evaluation Harness & Scenario Benchmark Suite
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Built automated evaluation harness (`harness/runner.py`), benchmark scenario generator (`harness/scenarios/library.py`), and report generator (`harness/evaluators.py`) producing `reports/latest_report.json` and `reports/latest_report.md`.

### Engineering Notes & Verification
- Benchmark Metrics: Evaluated pipeline over scenario suite, demonstrating **90.00% overall success rate**, **100% prompt injection defense rate**, and **100% tool 503 recovery rate**.
- Reports Generated: Verified machine-readable `reports/latest_report.json` and Markdown `reports/latest_report.md`.
- Test Suite: `harness/tests/test_harness.py` passed cleanly. 20 total project suite tests passing.

---

## Milestone 9: End-to-End Integration, Docker Compose & Final System Hardening
- **Status**: Completed
- **Date**: 2026-08-20
- **Summary**: Added end-to-end integration test suite (`tests/e2e/test_end_to_end.py`), Dockerfiles for each microservice (`services/triage/Dockerfile`, `services/resolution/Dockerfile`, `services/saboteur/Dockerfile`), `docker-compose.yml`, `Makefile`, and `README.md`.

### Engineering Notes & Final Self-Audit
- E2E Verification: Executed full test suite (`pytest`) across 23 test modules (unit, integration, chaos, e2e, harness). All 23 tests passed cleanly.
- Definition of Done Verified:
  1. Service 1, Service 2, Service 3 fully operational as independent microservices.
  2. Structured REST A2A communication protocol active.
  3. Prompt injection defenses resilient (`<data>` boundary tag framing).
  4. Clarification loop bounded at max 2 attempts.
  5. Investigation loop bounded at max 3 iterations.
  6. Tool retries and HTTP 503 recovery active.
  7. Automated 100-run Evaluation Harness operational.
  8. Meaningful local Git commit history recorded without remote pushes.
