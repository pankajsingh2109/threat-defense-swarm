import pytest
from pathlib import Path
from shared.unresolved_queue import (
    add_unresolved_case,
    get_unresolved_cases,
    mark_case_resolved,
    get_queue_stats,
    get_case_by_id
)

@pytest.fixture
def temp_queue(tmp_path):
    return tmp_path / "test_unresolved_queue.json"


def test_add_and_get_unresolved_case(temp_queue):
    case = add_unresolved_case(
        run_id="run_test_001",
        threat_id="threat-abc12345",
        raw_text="Failed login from 203.0.113.7 x40",
        source="firewall",
        sanitization_flagged=False,
        intent="threat",
        intent_category="brute_force",
        intent_confidence=0.95,
        failure_reason="A2A Communication failure: Connection refused",
        queue_path=temp_queue
    )

    assert case["threat_id"] == "threat-abc12345"
    assert case["status"] == "pending"

    # Query pending cases
    pending = get_unresolved_cases(status="pending", queue_path=temp_queue)
    assert len(pending) == 1
    assert pending[0]["threat_id"] == "threat-abc12345"

    stats = get_queue_stats(queue_path=temp_queue)
    assert stats["total_cases"] == 1
    assert stats["pending_cases"] == 1
    assert stats["resolved_cases"] == 0


def test_mark_case_resolved(temp_queue):
    add_unresolved_case(
        run_id="run_test_002",
        threat_id="threat-xyz98765",
        raw_text="Suspicious brute-force attack",
        queue_path=temp_queue
    )

    success = mark_case_resolved(
        threat_id="threat-xyz98765",
        verdict="block_ip",
        reason="Resolved after Service 2 recovery with high confidence malicious IP.",
        queue_path=temp_queue
    )
    assert success is True

    resolved_case = get_case_by_id("threat-xyz98765", queue_path=temp_queue)
    assert resolved_case is not None
    assert resolved_case["status"] == "resolved"
    assert resolved_case["resolved_verdict"] == "block_ip"
    assert resolved_case["resolved_at"] is not None

    stats = get_queue_stats(queue_path=temp_queue)
    assert stats["pending_cases"] == 0
    assert stats["resolved_cases"] == 1
