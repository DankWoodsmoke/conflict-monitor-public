import logging
import asyncio
from urllib.parse import urlsplit
from app.config import settings

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.broadcaster import broadcaster

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    origin = ws.headers.get("origin")
    allowed = {s.strip() for s in settings.cors_origins.split(",") if s.strip()} or {"http://localhost:5173", "http://127.0.0.1:5173"}
    if origin:
        try:
            parsed = urlsplit(origin)
            valid = (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                     and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment)
            trusted = valid and (origin in allowed or parsed.netloc == ws.headers.get("host"))
        except ValueError:
            trusted = False
        if not trusted:
            await ws.close(code=1008)
            return
    if not await broadcaster.connect(ws):
        return
    try:
        while True:
            # Keep connection alive; client can send pings
            message = await ws.receive_text()
            if len(message) > 4096:
                await ws.close(code=1009)
                return
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await broadcaster.disconnect(ws)
