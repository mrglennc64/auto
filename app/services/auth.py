from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select

from app.models import Tenant
from app.models.db import session_scope
from config.settings import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_basic = HTTPBasic()


def _is_active_tenant_key(api_key: str) -> bool:
    """Look up the key against active tenants. Cheap (indexed unique col)."""
    with session_scope() as s:
        row = s.scalars(
            select(Tenant).where(Tenant.api_key == api_key, Tenant.status == "active")
        ).one_or_none()
    return row is not None


def verify_api_key(api_key: str | None = Depends(_api_key_header)) -> str:
    """Accept either a global API key from settings.api_key_set OR a
    per-tenant key stored on the tenants table (status='active')."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    if api_key in settings.api_key_set:
        return api_key
    if _is_active_tenant_key(api_key):
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
    )


def verify_dashboard_basic(creds: HTTPBasicCredentials = Depends(_basic)) -> str:
    user_ok = secrets.compare_digest(creds.username, settings.dashboard_user)
    pass_ok = secrets.compare_digest(creds.password, settings.dashboard_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username
