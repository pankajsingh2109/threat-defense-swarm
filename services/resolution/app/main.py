import time
import httpx
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Path
from shared.config import settings
from shared.logger import setup_logger
from shared.schemas.a2a import A2AEnvelope, A2AContext, MessageType
from shared.schemas.events import TerminalResult, Verdict
from shared.schemas.tools import IPReputationResponse, GeoLookupResponse, AuthFrequencyResponse
from shared.resilience import IdempotencyCache, execute_with_retry
from services.resolution.app.mock_tools import get_ip_reputation, get_geo_lookup, get_auth_frequency
from services.resolution.app.clarification import handle_clarification_loop
from services.resolution.app.investigator import decide_evidence_sufficiency, decide_final_verdict

logger = setup_logger("service-2-resolution")
app = FastAPI(title="Service 2 — Resolution Agent", version="1.0.0")

idempotency_cache = IdempotencyCache(max_items=1000)
MAX_INVESTIGATION_ITERATIONS = 3

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "resolution"}

# Mock Security Tool Endpoints
@app.get("/tools/ip-reputation/{ip}", response_model=IPReputationResponse)
def api_ip_reputation(ip: str = Path(...)):
    return get_ip_reputation(ip)

@app.get("/tools/geo-lookup/{ip}", response_model=GeoLookupResponse)
def api_geo_lookup(ip: str = Path(...)):
    return get_geo_lookup(ip)

@app.get("/tools/auth-frequency/{ip}", response_model=AuthFrequencyResponse)
def api_auth_frequency(ip: str = Path(...)):
    return get_auth_frequency(ip)

@app.post("/a2a/investigate")
async def investigate_threat(envelope: A2AEnvelope):
    """
    Receives compressed A2A context, validates schema, executes bounded clarification loop if needed,
    runs bounded investigation loop with resilient tool calls, and produces final verdict.
    """
    start_time = time.time()
    
    # Idempotency Protection
    cache_key = f"{envelope.threat_id}:{envelope.message_id}"
    if idempotency_cache.has(cache_key):
        logger.info(f"Idempotent cache hit for key: {cache_key}")
        return idempotency_cache.get(cache_key)

    context = A2AContext(**envelope.payload)
    logger.info(f"Processing investigation request for threat: {context.threat_id}", extra={"threat_id": context.threat_id})

    chaos_events = []
    if context.flags.injection_detected:
        chaos_events.append("prompt_injection_defended")

    # Step 1: Bounded Clarification Loop (max 2 attempts)
    context, clar_attempts, is_resolved = await handle_clarification_loop(context)
    if not is_resolved or not context.source_ip:
        latency_ms = (time.time() - start_time) * 1000
        res = TerminalResult(
            threat_id=context.threat_id,
            verdict=Verdict.INSUFFICIENT_CONTEXT,
            reason="Bounded clarification loop exhausted (max 2 attempts) with missing IP data.",
            confidence=0.0,
            latency_ms=latency_ms,
            chaos_events=chaos_events,
            clarification_attempts=clar_attempts,
            investigation_iterations=0,
            success=False
        )
        idempotency_cache.set(cache_key, res)
        return res

    # Step 2: Bounded Investigation Loop (max 3 iterations)
    evidence: List[Dict[str, Any]] = []
    investigation_iterations = 0

    for iteration in range(1, MAX_INVESTIGATION_ITERATIONS + 1):
        investigation_iterations = iteration
        logger.info(f"Investigation loop iteration {iteration}/{MAX_INVESTIGATION_ITERATIONS} for threat: {context.threat_id}")

        # Execute mock tool lookup based on iteration
        tool_name = "ip_reputation" if iteration == 1 else ("auth_frequency" if iteration == 2 else "geo_lookup")
        tool_url = f"{settings.resolution_url}/tools/{tool_name.replace('_', '-')}/{context.source_ip}"

        async def _call_tool():
            # Local in-process lookup or HTTP fallback
            if tool_name == "ip_reputation":
                return get_ip_reputation(context.source_ip).model_dump()
            elif tool_name == "auth_frequency":
                return get_auth_frequency(context.source_ip).model_dump()
            else:
                return get_geo_lookup(context.source_ip).model_dump()

        try:
            tool_result = await execute_with_retry(_call_tool, max_retries=3, initial_delay=0.05)
            evidence.append({tool_name: tool_result})
        except Exception as e:
            logger.warning(f"Tool call {tool_name} failed after retries: {e}")
            chaos_events.append("tool_503_exhausted")

        # LLM Call #2: Evaluate Evidence Sufficiency
        sufficiency = await decide_evidence_sufficiency(iteration, context, evidence)
        if sufficiency.sufficient_evidence or iteration >= MAX_INVESTIGATION_ITERATIONS:
            logger.info(f"Evidence sufficiency reached at iteration {iteration}")
            break

    # Step 3: LLM Call #3: Final Verdict
    final_verdict = await decide_final_verdict(context, evidence)
    latency_ms = (time.time() - start_time) * 1000

    terminal_result = TerminalResult(
        threat_id=context.threat_id,
        verdict=final_verdict.verdict,
        reason=final_verdict.reason,
        confidence=final_verdict.confidence,
        latency_ms=latency_ms,
        chaos_events=chaos_events,
        clarification_attempts=clar_attempts,
        investigation_iterations=investigation_iterations,
        success=True
    )

    idempotency_cache.set(cache_key, terminal_result)
    return terminal_result
