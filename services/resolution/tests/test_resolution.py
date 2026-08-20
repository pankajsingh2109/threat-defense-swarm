import pytest
from services.resolution.app.mock_tools import get_ip_reputation, get_geo_lookup, get_auth_frequency
from services.resolution.app.investigator import mock_decide_sufficiency, mock_decide_verdict
from shared.schemas.tools import ReputationStatus
from shared.schemas.events import Verdict
from shared.schemas.a2a import A2AContext

def test_mock_tools():
    rep = get_ip_reputation("203.0.113.7")
    assert rep.reputation == ReputationStatus.MALICIOUS
    assert rep.reports == 12

    geo = get_geo_lookup("198.51.100.1")
    assert geo.country == "US"
    assert geo.city == "Dallas"

    auth = get_auth_frequency("203.0.113.7")
    assert auth.attempts_last_hour == 150

def test_investigation_sufficiency_logic():
    s1 = mock_decide_sufficiency(1, [])
    assert s1.sufficient_evidence is False

    s2 = mock_decide_sufficiency(1, [{"reputation": ReputationStatus.MALICIOUS}])
    assert s2.sufficient_evidence is True

def test_final_verdict_logic():
    ctx = A2AContext(
        threat_id="threat-001",
        source_ip="203.0.113.7",
        event_type="brute_force_login",
        confidence=0.92,
        raw_excerpt="Failed login"
    )
    evidence = [{"reputation": ReputationStatus.MALICIOUS}]
    verdict = mock_decide_verdict(ctx, evidence)
    assert verdict.verdict == Verdict.BLOCK_IP
    assert verdict.confidence == 0.92
