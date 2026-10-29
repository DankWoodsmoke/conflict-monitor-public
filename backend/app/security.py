"""Shared fail-closed authorization for maintenance and paid operations."""
import secrets
from fastapi import Header, HTTPException
from app.config import settings


async def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    expected = settings.admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Administrative operations are disabled")
    try:
        authorized = bool(x_admin_key) and secrets.compare_digest(x_admin_key, expected)
    except TypeError:
        # HTTP field values may contain non-ASCII bytes. compare_digest rejects
        # non-ASCII strings; malformed credentials are forbidden, not a 500.
        authorized = False
    if not authorized:
        raise HTTPException(status_code=403, detail="Administrative authorization required")
