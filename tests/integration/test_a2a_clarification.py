import pytest
from httpx import AsyncClient, ASGITransport
from services.triage.app.main import app as triage_app
from services.resolution.app.main import app as resolution_app
from shared.schemas.events import RawStreamItem, Verdict
from shared.schemas.a2a import A2AEnvelope, A2AContext, MessageType
from shared.utilities.http import set_override_clients

@pytest.mark.asyncio
async def test_a2a_full_flow_threat():
    """Test full pipeline execution from raw threat stream item to final resolution verdict."""
    resolution_transport = ASGITransport(app=resolution_app)

    async with AsyncClient(transport=resolution_transport, base_url="http://test") as res_client:
        ctx = A2AContext(
            threat_id="threat-a2a-001",
            source_ip="203.0.113.7",
            event_type="brute_force_login",
            confidence=0.92,
            raw_excerpt="Failed login from 203.0.113.7 x40"
        )
        envelope = A2AEnvelope(
            threat_id="threat-a2a-001",
            sender="triage-agent",
            recipient="resolution-agent",
            message_type=MessageType.INVESTIGATION_REQUEST,
            payload=ctx.model_dump()
        )
        response = await res_client.post("/a2a/investigate", json=envelope.model_dump())
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == Verdict.BLOCK_IP
        assert data["success"] is True

@pytest.mark.asyncio
async def test_bounded_clarification_loop_termination():
    """Test clarification loop terminates strictly after max 2 attempts when data is unresolvable."""
    triage_transport = ASGITransport(app=triage_app)
    resolution_transport = ASGITransport(app=resolution_app)

    async with AsyncClient(transport=triage_transport, base_url="http://localhost:8001") as triage_client:
        async with AsyncClient(transport=resolution_transport, base_url="http://test") as res_client:
            set_override_clients(triage_client=triage_client)
            try:
                ctx = A2AContext(
                    threat_id="threat-missing-ip-002",
                    source_ip=None,
                    event_type="ambiguous_event",
                    confidence=0.60,
                    raw_excerpt="Incomplete log line without IP"
                )
                envelope = A2AEnvelope(
                    threat_id="threat-missing-ip-002",
                    sender="triage-agent",
                    recipient="resolution-agent",
                    message_type=MessageType.INVESTIGATION_REQUEST,
                    payload=ctx.model_dump()
                )
                response = await res_client.post("/a2a/investigate", json=envelope.model_dump())
                assert response.status_code == 200
                data = response.json()
                assert data["verdict"] == Verdict.INSUFFICIENT_CONTEXT
                assert data["clarification_attempts"] == 2
                assert data["success"] is False
            finally:
                set_override_clients(triage_client=None)
