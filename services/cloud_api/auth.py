"""
VitaScribe Cloud API - Authentication

API key authentication via the X-API-Key header.

Keys:
  API_USERS  "naam:sleutel,naam2:sleutel2"  one key per user (preferred);
             the name appears in the usage log, so access can be traced and
             one workplace can be switched off without touching the others.
  API_KEYS   "sleutel1,sleutel2"            legacy shared keys (user "gedeeld").
  register   keys of practices with a licence (DATABASE_URL); see licentie.py.
Open mode: no keys and no register allows every request (user "dev"), but only
when VITASCRIBE_OPEN=1 is set explicitly. Without it such a server refuses all
calls, so a deploy that lost its keys fails closed instead of open.
"""

from __future__ import annotations

import hmac
import os
from typing import Dict, Optional

from fastapi import Header, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from .config import get_config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _key_table() -> Dict[str, str]:
    """key -> user name."""
    table: Dict[str, str] = {}
    for entry in (os.getenv("API_USERS") or "").split(","):
        if ":" in entry:
            name, key = entry.split(":", 1)
            if name.strip() and key.strip():
                table[key.strip()] = name.strip()
    for key in get_config().api_keys.split(","):
        if key.strip():
            table.setdefault(key.strip(), "gedeeld")
    return table


def open_mode() -> bool:
    """Open mode must be switched on by hand, for local development only."""
    return (os.getenv("VITASCRIBE_OPEN") or "").strip() == "1"


def user_for_key(api_key: str) -> Optional[str]:
    """User name for an environment key, "dev" in open mode, None otherwise.
    Register keys are looked up asynchronously in licentie.identificeer."""
    from . import register

    table = _key_table()
    if not table and not register.actief():
        return "dev" if open_mode() else None
    for key, name in table.items():
        if api_key and hmac.compare_digest(key, api_key):
            return name
    return None


def is_valid_api_key(api_key: str) -> bool:
    return user_for_key(api_key) is not None


# Answered in any mode: here the extension learns which modes are allowed.
MODUS_VRIJ = ("/api/v1/providers",)


async def huidige_identiteit(
    request: Request,
    api_key: str = Security(api_key_header),
    praktijk: Optional[str] = Header(default=None, alias="X-Bricks-Praktijk"),
):
    """Who is calling, with the licence of their practice. Raises 401/403 with a
    message the doctor can act on, also when the chosen mode is not allowed for
    this practice (TOEGESTANE_MODI, "alleen EU-modus")."""
    from . import audit, data_policy, licentie

    try:
        ident = await licentie.identificeer(api_key, praktijk)
    except licentie.LicentieFout as fout:
        raise HTTPException(status_code=fout.status, detail=fout.detail)
    if request is not None and request.url.path not in MODUS_VRIJ:
        weigering = data_policy.modus_weigering(ident)
        if weigering:
            audit.log_event(ident.label, "modus.geweigerd", mode=data_policy.modus())
            raise HTTPException(status_code=403, detail=weigering)
    return ident


async def verify_api_key(
    request: Request,
    api_key: str = Security(api_key_header),
    praktijk: Optional[str] = Header(default=None, alias="X-Bricks-Praktijk"),
) -> str:
    """Validate the key and return the user name (for the usage log)."""
    return (await huidige_identiteit(request, api_key, praktijk)).label
