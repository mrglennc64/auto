from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials

from config.settings import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_basic = HTTPBasic()


def verify_api_key(api_key: str | None = Depends(_api_key_header)) -> str:
    if not api_key or api_key not in settings.api_key_set:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


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
