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
from shared.unresolved_queue import add_unresolved_case
from shared.utilities.http import get_resolution_client
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
        return {
            "run_id": item.run_id,
            "threat_id": threat_id,
            "source": item.source,
            "raw_text": item.raw_text,
            "sanitization_flagged": sanitized.injection_flagged,
            "flag_reason": sanitized.flag_reason,
            "intent": classification.intent.value,
            "intent_category": classification.category,
            "intent_confidence": classification.confidence,
            "verdict": Verdict.ALLOW.value,
            "reason": f"Classified as noise/benign activity ({classification.category})",
            "confidence": classification.confidence,
            "latency_ms": round(latency_ms, 2),
            "chaos_events": ["prompt_injection_defended"] if sanitized.injection_flagged else [],
            "clarification_attempts": 0,
            "investigation_iterations": 0,
            "success": True
        }

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
        override = get_resolution_client()
        if override is not None:
            resp = await override.post("/a2a/investigate", json=envelope.model_dump())
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Service 2 error: {resp.text}")
            return resp.json()
        else:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(resolution_endpoint, json=envelope.model_dump())
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"Service 2 error: {resp.text}")
                return resp.json()

    try:
        response_data = await execute_with_retry(_send_a2a, max_retries=3, initial_delay=0.05)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(response_data, dict):
            response_data["run_id"] = item.run_id
            response_data["source"] = item.source
            response_data["raw_text"] = item.raw_text
            response_data["sanitization_flagged"] = sanitized.injection_flagged
            response_data["flag_reason"] = sanitized.flag_reason
            response_data["intent"] = classification.intent.value
            response_data["intent_category"] = classification.category
            response_data["intent_confidence"] = classification.confidence
            response_data["latency_ms"] = round(latency_ms, 2)
            
            chaos_evs = response_data.get("chaos_events", [])
            if sanitized.injection_flagged and "prompt_injection_defended" not in chaos_evs:
                chaos_evs.append("prompt_injection_defended")
            response_data["chaos_events"] = chaos_evs
            return response_data
        return response_data
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        fail_msg = f"A2A Communication failure: {e}"
        logger.error(f"Failed to communicate with Resolution Agent after retries: {e}", extra={"threat_id": threat_id})
        
        # Save to Dead-Letter Queue for deferred resolution
        add_unresolved_case(
            run_id=item.run_id,
            threat_id=threat_id,
            raw_text=item.raw_text,
            source=item.source,
            sanitization_flagged=sanitized.injection_flagged,
            flag_reason=sanitized.flag_reason,
            intent=classification.intent.value,
            intent_category=classification.category,
            intent_confidence=classification.confidence,
            failure_reason=fail_msg
        )

        return {
            "run_id": item.run_id,
            "threat_id": threat_id,
            "source": item.source,
            "raw_text": item.raw_text,
            "sanitization_flagged": sanitized.injection_flagged,
            "flag_reason": sanitized.flag_reason,
            "intent": classification.intent.value,
            "intent_category": classification.category,
            "intent_confidence": classification.confidence,
            "verdict": Verdict.UNRESOLVED.value,
            "reason": fail_msg,
            "confidence": 0.0,
            "latency_ms": round(latency_ms, 2),
            "chaos_events": ["a2a_packet_dropped_retried"],
            "clarification_attempts": 0,
            "investigation_iterations": 0,
            "success": False
        }

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
