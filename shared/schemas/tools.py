from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ReputationStatus(str, Enum):
    MALICIOUS = "malicious"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    TRUSTED = "trusted"
    UNKNOWN = "unknown"

class IPReputationResponse(BaseModel):
    ip: str
    reputation: ReputationStatus
    reports: int

class GeoLookupResponse(BaseModel):
    ip: str
    country: str
    city: str
    is_vpn: bool

class AuthFrequencyResponse(BaseModel):
    ip: str
    attempts_last_hour: int
    unique_usernames: int
