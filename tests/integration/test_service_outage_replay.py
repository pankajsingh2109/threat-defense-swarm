import pytest
from httpx import AsyncClient, ASGITransport
from services.triage.app.main import app as triage_app
from services.resolution.app.main import app as resolution_app
from shared.schemas.events import RawStreamItem, Verdict
from shared.utilities.http import set_override_clients
from shared.unresolved_queue import get_unresolved_cases, mark_case_resolved
from harness.replay import replay_all_pending_cases

@pytest.mark.asyncio
async def test_service_2_down_triggers_unresolved_and_replay():
    """
    Simulates Service 2 being offline/failing:
    1. Triage Agent fails to connect to Resolution Agent.
    2. Event returns UNRESOLVED and is archived in Dead-Letter Queue.
    3. Service 2 comes back online.
    4. Replay resolves the queued event.
    """
    triage_transport = ASGITransport(app=triage_app)

    # 1. Triage runs without a valid Resolution Client (simulating Service 2 down)
    async with AsyncClient(transport=triage_transport, base_url="http://localhost:8001") as triage_client:
        set_override_clients(triage_client=triage_client, resolution_client=None)
        
        item = RawStreamItem(
            source="firewall_log",
            raw_text="Multiple failed SSH root logins from 203.0.113.7 in 1 minute",
            run_id="test_outage_001"
        )
        
        resp = await triage_client.post("/ingest", json=item.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        
        # Must be unresolved
        assert data["verdict"] == Verdict.UNRESOLVED.value
        assert data["success"] is False
        assert "A2A Communication failure" in data["reason"]

        threat_id = data["threat_id"]

        # Check Dead-Letter Queue
        pending_cases = get_unresolved_cases(status="pending")
        matching = [c for c in pending_cases if c["threat_id"] == threat_id]
        assert len(matching) >= 1
        assert matching[0]["status"] == "pending"

    # 2. Service 2 comes online and replay engine processes pending queue
    replay_summary = await replay_all_pending_cases(use_inprocess_fallback=True)
    assert replay_summary["resolved"] >= 1

    # Verify that case is now marked resolved
    resolved_cases = get_unresolved_cases(status="resolved")
    resolved_matching = [c for c in resolved_cases if c["threat_id"] == threat_id]
    assert len(resolved_matching) >= 1
    assert resolved_matching[0]["status"] == "resolved"
    assert resolved_matching[0]["resolved_verdict"] in [Verdict.BLOCK_IP.value, Verdict.QUARANTINE.value]
