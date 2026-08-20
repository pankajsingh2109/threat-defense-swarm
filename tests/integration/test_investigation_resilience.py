import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from services.resolution.app.main import app as resolution_app
from shared.schemas.events import Verdict
from shared.schemas.a2a import A2AEnvelope, A2AContext, MessageType

@pytest.mark.asyncio
async def test_investigation_loop_capped_at_three():
    """Test investigation loop does not exceed 3 iterations."""
    resolution_transport = ASGITransport(app=resolution_app)

    async with AsyncClient(transport=resolution_transport, base_url="http://test") as res_client:
        ctx = A2AContext(
            threat_id="threat-inv-001",
            source_ip="198.51.100.1",
            event_type="suspicious_login",
            confidence=0.70,
            raw_excerpt="Suspicious login attempt"
        )
        envelope = A2AEnvelope(
            threat_id="threat-inv-001",
            sender="triage-agent",
            recipient="resolution-agent",
            message_type=MessageType.INVESTIGATION_REQUEST,
            payload=ctx.model_dump()
        )
        
        response = await res_client.post("/a2a/investigate", json=envelope.model_dump())
        assert response.status_code == 200
        data = response.json()
        assert data["investigation_iterations"] <= 3
        assert data["success"] is True

@pytest.mark.asyncio
async def test_tool_failure_retry_and_graceful_degradation():
    """Test resilient recovery and graceful fallback when tool calls fail with 503."""
    resolution_transport = ASGITransport(app=resolution_app)

    attempts = 0
    def failing_reputation_tool(ip: str):
        nonlocal attempts
        attempts += 1
        raise Exception("HTTP 503 Service Unavailable")

    async with AsyncClient(transport=resolution_transport, base_url="http://test") as res_client:
        with patch("services.resolution.app.main.get_ip_reputation", side_effect=failing_reputation_tool):
            ctx = A2AContext(
                threat_id="threat-503-002",
                source_ip="203.0.113.7",
                event_type="brute_force_login",
                confidence=0.90,
                raw_excerpt="Failed login 503 test"
            )
            envelope = A2AEnvelope(
                threat_id="threat-503-002",
                sender="triage-agent",
                recipient="resolution-agent",
                message_type=MessageType.INVESTIGATION_REQUEST,
                payload=ctx.model_dump()
            )

            response = await res_client.post("/a2a/investigate", json=envelope.model_dump())
            assert response.status_code == 200
            data = response.json()
            assert "tool_503_exhausted" in data["chaos_events"]
            assert data["success"] is True
