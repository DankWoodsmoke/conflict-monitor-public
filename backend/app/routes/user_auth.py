"""
User-provided Telegram credential auth endpoints.
===================================================
Implements the "bring your own keys" architecture:
  - Users supply their Telegram API ID, hash, and phone via the frontend UI.
  - Credentials are stored in the USER'S BROWSER localStorage — never on the server.
  - These endpoints accept credentials per-request and never persist them.
  - After successful auth, a StringSession string is returned to the client and
    stored in localStorage.  The client passes it as a header on subsequent requests.

Flow:
  1. POST /auth/telegram/start   → { api_id, api_hash, phone } in body
     Server: starts Telethon auth, sends SMS/app code
     Returns: { session_token } (opaque key to resume auth), { phone_code_hash }

  2. POST /auth/telegram/verify  → { session_token, code, phone_code_hash }
     Server: completes auth, returns StringSession string
     Returns: { session_string }

  3. GET  /auth/telegram/status  → Header: X-Telegram-Session: <session_string>
     Returns: { connected: bool, phone: str }

The session_token is an ephemeral server-side key (UUID) that maps to an in-progress
TelegramClient connection. It expires in 10 minutes if unused.
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    FloodWaitError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/telegram", tags=["auth"])

# ── In-memory pending auth sessions ─────────────────────────────────────────
# Maps session_token → { client, phone_code_hash, api_id, api_hash, created_at }
# Entries expire after 10 minutes to prevent memory leaks.

_PENDING: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 minutes


def _cleanup_expired():
    """Remove pending sessions older than TTL."""
    now = time.time()
    expired = [k for k, v in _PENDING.items() if now - v["created_at"] > _PENDING_TTL]
    for k in expired:
        try:
            client = _PENDING[k].get("client")
            if client:
                asyncio.create_task(client.disconnect())
        except Exception:
            pass
        del _PENDING[k]


# ── Request / response models ────────────────────────────────────────────────

class StartAuthRequest(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class StartAuthResponse(BaseModel):
    session_token: str
    phone_code_hash: str
    message: str = "Verification code sent. Check your Telegram app or SMS."

class VerifyAuthRequest(BaseModel):
    session_token: str
    code: str
    phone_code_hash: str
    password: Optional[str] = None  # For 2FA-enabled accounts

class VerifyAuthResponse(BaseModel):
    session_string: str
    phone: str
    message: str = "Authentication successful."

class AuthStatusResponse(BaseModel):
    connected: bool
    phone: Optional[str] = None
    message: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartAuthResponse)
async def start_auth(req: StartAuthRequest):
    """
    Begin Telegram authentication.
    Sends a verification code to the user's phone/app.
    Returns a session_token to be passed to /verify.
    """
    _cleanup_expired()

    if not req.api_id or not req.api_hash or not req.phone:
        raise HTTPException(status_code=400, detail="api_id, api_hash, and phone are required.")

    # Validate api_id is a positive integer
    if req.api_id <= 0:
        raise HTTPException(status_code=400, detail="api_id must be a positive integer.")

    try:
        client = TelegramClient(
            StringSession(),
            req.api_id,
            req.api_hash,
        )
        await client.connect()

        result = await client.send_code_request(req.phone)
        phone_code_hash = result.phone_code_hash

        token = str(uuid.uuid4())
        _PENDING[token] = {
            "client": client,
            "phone": req.phone,
            "phone_code_hash": phone_code_hash,
            "api_id": req.api_id,
            "api_hash": req.api_hash,
            "created_at": time.time(),
        }

        logger.info("Auth started for phone %s...%s", req.phone[:4], req.phone[-2:])
        return StartAuthResponse(session_token=token, phone_code_hash=phone_code_hash)

    except FloodWaitError as e:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Please wait {e.seconds} seconds before retrying."
        )
    except Exception as e:
        logger.error("Auth start failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to start authentication: {str(e)}")


@router.post("/verify", response_model=VerifyAuthResponse)
async def verify_auth(req: VerifyAuthRequest):
    """
    Complete Telegram authentication with the verification code.
    Returns a StringSession string to store in localStorage.
    """
    pending = _PENDING.get(req.session_token)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please start authentication again."
        )

    # Check TTL
    if time.time() - pending["created_at"] > _PENDING_TTL:
        del _PENDING[req.session_token]
        raise HTTPException(
            status_code=410,
            detail="Authentication session expired. Please start again."
        )

    client: TelegramClient = pending["client"]

    try:
        await client.sign_in(
            phone=pending["phone"],
            code=req.code,
            phone_code_hash=req.phone_code_hash,
        )
    except SessionPasswordNeededError:
        if not req.password:
            raise HTTPException(
                status_code=401,
                detail="Two-factor authentication is enabled. Please provide your 2FA password."
            )
        try:
            await client.sign_in(password=req.password)
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"2FA password incorrect: {str(e)}")
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=400, detail="Verification code is incorrect.")
    except PhoneCodeExpiredError:
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please start authentication again."
        )
    except Exception as e:
        logger.error("Auth verify failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

    # Export session string
    session_string = client.session.save()
    phone = pending["phone"]

    # Clean up pending entry
    del _PENDING[req.session_token]
    await client.disconnect()

    logger.info("Auth successful for phone %s...%s", phone[:4], phone[-2:])
    return VerifyAuthResponse(session_string=session_string, phone=phone)


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(x_telegram_session: Optional[str] = Header(default=None)):
    """
    Check if a stored session string is still valid.
    Pass the session string as X-Telegram-Session header.
    """
    if not x_telegram_session:
        return AuthStatusResponse(connected=False, message="No session provided.")

    # Get api_id and api_hash from environment (server's own keys for status checks)
    # In bring-your-own-keys mode, users pass their own keys via headers too.
    # For status checks we'd need the keys — accept them as optional headers or
    # fall back to server defaults for validation.
    api_id_env = os.getenv("TELEGRAM_API_ID")
    api_hash_env = os.getenv("TELEGRAM_API_HASH")

    if not api_id_env or not api_hash_env:
        return AuthStatusResponse(
            connected=False,
            message="Server has no Telegram credentials configured. User credentials required."
        )

    try:
        client = TelegramClient(
            StringSession(x_telegram_session),
            int(api_id_env),
            api_hash_env,
        )
        await client.connect()
        me = await client.get_me()
        await client.disconnect()

        if me:
            phone = getattr(me, "phone", None)
            return AuthStatusResponse(
                connected=True,
                phone=f"+{phone}" if phone else None,
                message="Session is valid."
            )
        return AuthStatusResponse(connected=False, message="Session could not be validated.")
    except Exception as e:
        logger.debug("Session validation failed: %s", e)
        return AuthStatusResponse(connected=False, message=f"Session invalid: {str(e)[:80]}")
