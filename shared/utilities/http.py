import httpx
from typing import Optional

_override_triage_client: Optional[httpx.AsyncClient] = None
_override_resolution_client: Optional[httpx.AsyncClient] = None

def set_override_clients(triage_client: Optional[httpx.AsyncClient] = None, resolution_client: Optional[httpx.AsyncClient] = None):
    global _override_triage_client, _override_resolution_client
    _override_triage_client = triage_client
    _override_resolution_client = resolution_client

def get_triage_client() -> Optional[httpx.AsyncClient]:
    return _override_triage_client

def get_resolution_client() -> Optional[httpx.AsyncClient]:
    return _override_resolution_client
