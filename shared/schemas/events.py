from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Intent(str, Enum):
    THREAT = "threat"
    NOISE = "noise"

class Verdict(str, Enum):
    BLOCK_IP = "block_ip"
    QUARANTINE = "quarantine"
    MONITOR = "monitor"
    ALLOW = "allow"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    UNRESOLVED = "unresolved"

class RawStreamItem(BaseModel):
    source: str
    raw_text: str
    run_id: Optional[str] = None
    expected_verdict: Optional[str] = None

class SanitizedInput(BaseModel):
    raw_text: str
    injection_flagged: bool = False
    flag_reason: Optional[str] = None

class IntentClassification(BaseModel):
    intent: Intent
    category: str
    confidence: float = Field(ge=0.0, le=1.0)

class EvidenceSufficiency(BaseModel):
    sufficient_evidence: bool
    next_action: str

class FinalVerdictPayload(BaseModel):
    verdict: Verdict
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)

class TerminalResult(BaseModel):
    run_id: Optional[str] = None
    threat_id: str
    verdict: Verdict
    reason: str
    confidence: float
    latency_ms: float
    chaos_events: List[str] = Field(default_factory=list)
    clarification_attempts: int = 0
    investigation_iterations: int = 0
    success: bool = True
