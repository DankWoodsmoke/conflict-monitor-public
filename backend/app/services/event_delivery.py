"""Bounded publication of committed Event creation and deletion receipts."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import async_session

logger = logging.getLogger(__name__)
_state = {"status": "idle", "last_success_at": None, "last_published_at": None, "error_type": None}


def delivery_status():
    return dict(_state)


def _stamp():
    return datetime.now(timezone.utc).isoformat()


async def publish_once():
    # Context exit commits assignments and the counter before returning. A
    # cancelled/failed transaction leaves the same rows eligible for retry.
    async with asyncio.timeout(10), async_session() as session, session.begin():
        result = await session.execute(text("SELECT public.publish_event_deliveries()"))
        return result.scalar_one()


async def start_event_delivery():
    _state.update(status="starting", last_success_at=None, last_published_at=None, error_type=None)
    while True:
        try:
            count = await publish_once()
        except (TimeoutError, SQLAlchemyError, OSError) as exc:
            # asyncpg can raise native DNS/socket errors during connection
            # establishment before SQLAlchemy wraps a driver exception. Keep
            # the uncommitted receipts eligible for the same bounded retry.
            error_type = type(exc).__name__
            if _state["error_type"] != error_type:
                logger.warning("Report delivery publication unavailable (%s)", error_type)
            _state.update(status="retrying", error_type=error_type)
            await asyncio.sleep(2)
            continue
        if type(count) is not int or not -1 <= count <= 100:
            raise RuntimeError("Invalid report publication result")
        stamp = _stamp()
        _state.update(status="busy" if count == -1 else "ok", last_success_at=stamp, error_type=None)
        if count > 0:
            _state["last_published_at"] = stamp
        await asyncio.sleep(.05 if count == 100 else .5)
