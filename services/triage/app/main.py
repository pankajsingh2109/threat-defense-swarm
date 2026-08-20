import time
import uuid
import httpx
from fastapi import FastAPI, HTTPException
from shared.config import settings
from shared.logger import setup_logger
from shared.schemas.events import RawStreamItem, Intent, TerminalResult, Verdict
from shared.schemas.a2a import (
    A2AEnvelope, A2AContext, ClarificationRequest, ClarificationResponse, MessageType
)
from shared.resilience import execute_with_retry
from services.triage.app.sanitizer import sanitize_input
from services.triage.app.classifier import classify_intent, compress_context

logger = setup_logger("service-1-triage")
app = FastAPI(title="Service 1 — Triage Agent", version="1.0.0")

# In-memory store for active triage cases
_context_store = {}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "triage"}

@app.post("/ingest")
async def ingest_event(item: RawStreamItem):
    """
    Ingests raw security event item, sanitizes data, classifies security intent,
    and forwards actionable threats via A2A to Resolution Agent.
    """
    start_time = time.time()
    logger.info(f"Ingesting raw event from source: {item.source}", extra={"run_id": item.run_id})

    # Step 1: Input Sanitization & Guard
    sanitized = sanitize_input(item.raw_text)
    if sanitized.injection_flagged:
        logger.warning(
            f"Prompt injection flagged: {sanitized.flag_reason}",
            extra={"run_id": item.run_id, "event_type": "prompt_injection_flagged"}
        )

    # Step 2: Intent Classification
    classification = await classify_intent(sanitized)
    logger.info(
        f"Intent classified: {classification.intent} (category: {classification.category}, confidence: {classification.confidence})",
        extra={"run_id": item.run_id}
    )

    threat_id = f"threat-{uuid.uuid4().hex[:8]}"

    # Step 3: Actionability Decision
    if classification.intent == Intent.NOISE:
        latency_ms = (time.time() - start_time) * 1000
        logger.info("Event classified as NOISE. Terminating flow.", extra={"run_id": item.run_id, "threat_id": threat_id})
        return TerminalResult(
            run_id=item.run_id,
            threat_id=threat_id,
            verdict=Verdict.ALLOW,
            reason=f"Classified as noise/benign activity ({classification.category})",
            confidence=classification.confidence,
            latency_ms=latency_ms,
            chaos_events=["prompt_injection_defended"] if sanitized.injection_flagged else [],
            success=True
        )

    # Step 4: Context Compression
    a2a_context = compress_context(sanitized, classification, threat_id=threat_id)
    _context_store[threat_id] = {
        "raw_text": item.raw_text,
        "sanitized": sanitized,
        "context": a2a_context
    }

    # Step 5: Forward via REST A2A Protocol to Service 2
    envelope = A2AEnvelope(
        threat_id=threat_id,
        sender="triage-agent",
        recipient="resolution-agent",
        message_type=MessageType.INVESTIGATION_REQUEST,
        payload=a2a_context.model_dump()
    )

    resolution_endpoint = f"{settings.resolution_url}/a2a/investigate"
    
    async def _send_a2a():
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(resolution_endpoint, json=envelope.model_dump())
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Service 2 error: {resp.text}")
            return resp.json()

    try:
        response_data = await execute_with_retry(_send_a2a, max_retries=3, initial_delay=0.1)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(response_data, dict) and "verdict" in response_data:
            response_data["latency_ms"] = latency_ms
            if sanitized.injection_flagged and "chaos_events" in response_data:
                if "prompt_injection_defended" not in response_data["chaos_events"]:
                    response_data["chaos_events"].append("prompt_injection_defended")
            return response_data
        return response_data
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to communicate with Resolution Agent after retries: {e}", extra={"threat_id": threat_id})
        return TerminalResult(
            run_id=item.run_id,
            threat_id=threat_id,
            verdict=Verdict.UNRESOLVED,
            reason=f"A2A Communication failure: {e}",
            confidence=0.0,
            latency_ms=latency_ms,
            success=False
        )

@app.post("/a2a/clarify", response_model=ClarificationResponse)
async def clarify_request(req: ClarificationRequest):
    """Responds strictly to bounded clarification requests from Service 2."""
    logger.info(f"Received clarification request for threat: {req.threat_id}, needed: {req.clarification_needed}")
    case = _context_store.get(req.threat_id)
    provided_data = {}

    if case:
        raw_text = case["raw_text"]
        for field in req.clarification_needed:
            if field == "source_ip":
                import re
                match = re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", raw_text)
                if match:
                    provided_data["source_ip"] = match.group(0)

    return ClarificationResponse(
        threat_id=req.threat_id,
        provided_data=provided_data
    )
