from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    INVESTIGATION_REQUEST = "investigation_request"
    CLARIFICATION_REQUEST = "clarification_request"
    CLARIFICATION_RESPONSE = "clarification_response"
    INVESTIGATION_VERDICT = "investigation_verdict"
    ERROR_RESPONSE = "error_response"

class A2AFlags(BaseModel):
    injection_detected: bool = False
    flag_reason: Optional[str] = None

class A2AContext(BaseModel):
    """Compressed lean context payload passed from Service 1 to Service 2."""
    protocol_version: str = "1.0"
    message_type: MessageType = MessageType.INVESTIGATION_REQUEST
    threat_id: str
    source_ip: Optional[str] = None
    event_type: str
    occurrences: int = 1
    window_seconds: int = 60
    confidence: float = Field(ge=0.0, le=1.0)
    raw_excerpt: str
    flags: A2AFlags = Field(default_factory=A2AFlags)

class ClarificationRequest(BaseModel):
    message_type: MessageType = MessageType.CLARIFICATION_REQUEST
    threat_id: str
    clarification_needed: List[str]

class ClarificationResponse(BaseModel):
    message_type: MessageType = MessageType.CLARIFICATION_RESPONSE
    threat_id: str
    provided_data: Dict[str, Any]

class A2AEnvelope(BaseModel):
    """Standard versioned envelope for all agent-to-agent REST payloads."""
    protocol_version: str = "1.0"
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    threat_id: str
    sender: str
    recipient: str
    message_type: MessageType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, Any]
