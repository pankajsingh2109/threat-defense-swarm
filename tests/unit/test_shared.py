import pytest
import asyncio
from shared.schemas.a2a import A2AEnvelope, A2AContext, MessageType
from shared.schemas.events import Intent, Verdict, IntentClassification
from shared.schemas.tools import IPReputationResponse, ReputationStatus
from shared.resilience import IdempotencyCache, execute_with_retry

def test_a2a_envelope_serialization():
    ctx = A2AContext(
        threat_id="threat-123",
        source_ip="203.0.113.7",
        event_type="brute_force_login",
        confidence=0.95,
        raw_excerpt="Failed login from 203.0.113.7"
    )
    envelope = A2AEnvelope(
        threat_id="threat-123",
        sender="triage-agent",
        recipient="resolution-agent",
        message_type=MessageType.INVESTIGATION_REQUEST,
        payload=ctx.model_dump()
    )
    data = envelope.model_dump()
    assert data["protocol_version"] == "1.0"
    assert data["threat_id"] == "threat-123"
    assert data["payload"]["source_ip"] == "203.0.113.7"

def test_idempotency_cache():
    cache = IdempotencyCache(max_items=2)
    cache.set("key1", "val1")
    cache.set("key2", "val2")
    assert cache.has("key1")
    assert cache.get("key2") == "val2"
    
    # Trigger eviction
    cache.set("key3", "val3")
    assert not cache.has("key1")
    assert cache.has("key3")

@pytest.mark.asyncio
async def test_execute_with_retry_success():
    attempts = 0
    async def flaky_fn():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Transient error")
        return "success"

    res = await execute_with_retry(flaky_fn, max_retries=3, initial_delay=0.01)
    assert res == "success"
    assert attempts == 2
