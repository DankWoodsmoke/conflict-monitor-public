"""A read-only, committed-offset stream for reconnecting report clients."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Event
from app.schemas import EventRead

router = APIRouter(prefix="/events/delivery", tags=["event delivery"])
MAX_OFFSET = (1 << 63) - 1


class DeliveryBaseline(BaseModel):
    epoch: str
    after: str
    events: list[EventRead]


class DeliveryChange(BaseModel):
    offset: str
    event_id: int
    action: Literal["upsert", "delete"]
    event: EventRead | None


class DeliveryPage(BaseModel):
    epoch: str
    changes: list[DeliveryChange]
    next_after: str
    has_more: bool


async def delivery_snapshot(session):
    # State and all Event projections in a response share one database view.
    # Neither a concurrent purge nor publication can mix snapshots mid-page.
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    state = (await session.execute(text("""
        SELECT epoch, last_offset, retired_through FROM public.event_delivery_state WHERE singleton
    """))).one()
    stream = "demo" if settings.demo_mode else "live"
    return stream, f"{state.epoch}-{stream}", state.last_offset, state.retired_through


def visible_events(stream):
    return select(Event).where(Event.id > 0, Event.source != "situational",
                               Event.source == "demo" if stream == "demo" else Event.source != "demo")


@router.get("/baseline", response_model=DeliveryBaseline)
async def baseline(limit: int = Query(50, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    stream, epoch, last_offset, _ = await delivery_snapshot(session)
    result = await session.execute(visible_events(stream).order_by(Event.timestamp.desc(), Event.id.desc()).limit(limit))
    return {"epoch": epoch, "after": str(last_offset), "events": result.scalars().all()}


@router.get("/changes", response_model=DeliveryPage)
async def changes(
    epoch: str = Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    after: str = Query(pattern=r"^(0|[1-9][0-9]{0,18})$"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    offset = int(after)
    if offset > MAX_OFFSET:
        raise HTTPException(status_code=422, detail="Delivery offset exceeds the supported range")
    stream, current_epoch, last_offset, retired_through = await delivery_snapshot(session)
    reason = None
    if epoch != current_epoch:
        reason = "epoch_changed"
    elif offset < retired_through:
        reason = "cursor_expired"
    elif offset > last_offset:
        reason = "cursor_ahead"
    if reason is not None:
        raise HTTPException(status_code=409, detail={"code": "delivery_baseline_required", "reason": reason})

    rows = (await session.execute(text("""
        SELECT publication_offset, event_id, action FROM public.event_deliveries
        WHERE stream = :stream AND publication_offset > :offset
        ORDER BY publication_offset LIMIT :limit
    """), {"stream": stream, "offset": offset, "limit": limit + 1})).all()
    page = rows[:limit]
    upserts = {row.event_id for row in page if row.action == "upsert"}
    events = {}
    if upserts:
        result = await session.execute(visible_events(stream).where(Event.id.in_(upserts)))
        events = {event.id: event for event in result.scalars().all()}
    items = []
    for row in page:
        event = events.get(row.event_id) if row.action == "upsert" else None
        # An earlier creation may have been purged already. Report its missing
        # projection explicitly while preserving its acknowledged offset.
        items.append({"offset": str(row.publication_offset), "event_id": row.event_id,
                      "action": "upsert" if event is not None else "delete", "event": event})
    return {"epoch": current_epoch, "changes": items,
            "next_after": items[-1]["offset"] if items else after, "has_more": len(rows) > limit}
