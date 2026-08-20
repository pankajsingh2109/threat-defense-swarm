from fastapi import FastAPI, HTTPException
from shared.schemas.tools import (
    IPReputationResponse, ReputationStatus,
    GeoLookupResponse, AuthFrequencyResponse
)

# Simulated local deterministic security database
MOCK_REPUTATION_DB = {
    "203.0.113.7": {"reputation": ReputationStatus.MALICIOUS, "reports": 12},
    "198.51.100.1": {"reputation": ReputationStatus.SUSPICIOUS, "reports": 4},
    "192.168.1.1": {"reputation": ReputationStatus.TRUSTED, "reports": 0},
    "10.0.0.1": {"reputation": ReputationStatus.NEUTRAL, "reports": 0},
}

MOCK_GEO_DB = {
    "203.0.113.7": {"country": "Unknown", "city": "Anonymous Proxy", "is_vpn": True},
    "198.51.100.1": {"country": "US", "city": "Dallas", "is_vpn": False},
    "192.168.1.1": {"country": "US", "city": "Local Network", "is_vpn": False},
}

MOCK_AUTH_FREQ_DB = {
    "203.0.113.7": {"attempts_last_hour": 150, "unique_usernames": 12},
    "198.51.100.1": {"attempts_last_hour": 15, "unique_usernames": 2},
    "192.168.1.1": {"attempts_last_hour": 1, "unique_usernames": 1},
}

def get_ip_reputation(ip: str) -> IPReputationResponse:
    """Mock IP reputation tool lookup."""
    data = MOCK_REPUTATION_DB.get(ip, {"reputation": ReputationStatus.UNKNOWN, "reports": 0})
    return IPReputationResponse(
        ip=ip,
        reputation=data["reputation"],
        reports=data["reports"]
    )

def get_geo_lookup(ip: str) -> GeoLookupResponse:
    """Mock Geo lookup tool lookup."""
    data = MOCK_GEO_DB.get(ip, {"country": "Unknown", "city": "Unknown", "is_vpn": False})
    return GeoLookupResponse(
        ip=ip,
        country=data["country"],
        city=data["city"],
        is_vpn=data["is_vpn"]
    )

def get_auth_frequency(ip: str) -> AuthFrequencyResponse:
    """Mock authentication frequency lookup."""
    data = MOCK_AUTH_FREQ_DB.get(ip, {"attempts_last_hour": 1, "unique_usernames": 1})
    return AuthFrequencyResponse(
        ip=ip,
        attempts_last_hour=data["attempts_last_hour"],
        unique_usernames=data["unique_usernames"]
    )
