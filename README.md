# Threat Defense Swarm — Autonomous Cybersecurity Triage & Resolution System

Threat Defense Swarm is a distributed multi-agent microservice architecture designed for autonomous cybersecurity triage, investigation, resolution, defensive prompt engineering, and chaos resilience testing.

---

## 🏛️ System Architecture & Pipeline Flow

```
RAW STREAM ITEM
      │
      ▼
┌──────────────────────────────────────────────────────────┐
│ Service 1 — Triage Agent                                 │
│ 1. Sanitization & Guard (<data> Tag Boundary Framing)   │
│ 2. Intent Classification (Threat vs Noise)               │
│ 3. Actionability Gate (Noise -> Terminal Result)         │
│ 4. Context Compression (Lean A2AContext Payload)         │
└─────────────────────────────┬────────────────────────────┘
                              │ REST A2A Protocol (POST /a2a/investigate)
                              ▼
┌──────────────────────────────────────────────────────────┐
│ Service 2 — Resolution Agent                             │
│ 1. Envelope & Context Validation                         │
│ 2. Bounded Clarification Loop (Max 2 Attempts)           │
│ 3. Bounded Investigation Loop (Max 3 Iterations)         │
│    └─ Mock Tools (IP Reputation, Geo Lookup, Auth Freq) │
│ 4. Evidence Sufficiency & Final Verdict Decision         │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
                 FINAL STRUCTURED VERDICT

┌──────────────────────────────────────────────────────────┐
│ Service 3 — Saboteur / Chaos Injector (Async & Seedable) │
│ • Injects Prompt Injection Variants into Stream          │
│ • Drops A2A Transit Packets Randomly                     │
│ • Forces HTTP 503 Errors on Mock Security Tools          │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Microservices

1. **Service 1 — Triage Agent** (`services/triage/`)
   - Ingests raw security logs and reports.
   - Enforces data/instruction separation by framing input inside `<data>...</data>` boundaries.
   - Evaluates heuristic injection flags.
   - Classifies intent using OpenAI structured outputs (with deterministic fallback).
   - Produces compressed, lean `A2AContext` payloads.

2. **Service 2 — Resolution Agent** (`services/resolution/`)
   - Validates incoming `A2AEnvelope` and idempotency keys.
   - Executes a **bounded clarification loop** (max 2 attempts) to query missing metadata.
   - Runs a **bounded investigation loop** (max 3 iterations) calling mock security tools (`/tools/ip-reputation`, `/tools/geo-lookup`, `/tools/auth-frequency`).
   - Handles transient tool failures via exponential backoff retries.
   - Renders structured verdicts (`block_ip`, `quarantine`, `monitor`, `allow`, `insufficient_context`, `unresolved`).

3. **Service 3 — Saboteur / Chaos Injector** (`services/saboteur/`)
   - Runs asynchronously and independently.
   - Seedable random generation (`CHAOS_SEED`) for 100% reproducible benchmark evaluations.
   - Injectable fault modes: Prompt Injection, Packet Drops, and Tool HTTP 503s.

4. **Evaluation Harness** (`harness/`)
   - Benchmark scenario library generating 100 deterministic test cases across benign, threat, ambiguous, and injection scenarios.
   - Calculates latency percentiles (P50, P95, P99), success/failure rates, prompt defense success rates, and tool recovery rates.
   - Exports `reports/latest_report.json` and `reports/latest_report.md`.

---

## 🖥️ Streamlit SOC Dashboard & Control Room

Launch the unified SOC control room with interactive metrics, microservice lifecycle controls, dead-letter queue replayer, and RAG incident assistant:

```powershell
.\.venv\Scripts\streamlit run ui/app.py
```

### Key UI Features:
1. **🎛️ Swarm Control Room (Sidebar)**: Real-time health monitoring and one-click Start/Stop/Restart controls for Service 1 (Triage), Service 2 (Resolution), and Service 3 (Saboteur).
2. **📊 Executive SOC Dashboard**: Interactive telemetry cards, Plotly verdict donut charts, and latency percentiles (P50/P95/P99).
3. **🚀 Swarm Execution Center**: Trigger multi-scenario evaluation benchmarks or test custom raw security logs in real-time.
4. **🔄 Dead-Letter Queue & Replay Engine**: Tracks unresolved cases when Service 2 is down and offers one-click deferred re-triage once Service 2 is online.
5. **🤖 RAG Cybersecurity Assistant**: Natural-language conversational AI assistant that retrieves past run reports, unresolved backlogs, and architecture docs.

---

## 🛠️ Getting Started

### 1. Prerequisites
- Python 3.10+ installed.

### 2. Environment Setup
Create and activate Python virtual environment:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
CHAOS_ENABLED=true
CHAOS_SEED=12345
RUN_COUNT=100
```

### 4. Running Tests
Run full Pytest suite across unit, integration, chaos, and end-to-end tests:
```powershell
.\.venv\Scripts\python.exe -m pytest
```

### 5. Running Evaluation Benchmark (CLI)
Execute the automated evaluation harness directly:
```powershell
.\.venv\Scripts\python.exe harness/runner.py
```

### 6. Launching Streamlit UI
```powershell
.\.venv\Scripts\streamlit run ui/app.py
```
