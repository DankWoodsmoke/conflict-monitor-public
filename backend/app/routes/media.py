"""GET /media/intel — recent chart/image captures from analytical X accounts."""
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.db import async_session
from app.models import IntelMedia

router = APIRouter(prefix="/media", tags=["media"])


def _media_to_dict(m: IntelMedia) -> dict:
    return {
        "id":          m.id,
        "tweet_id":    m.tweet_id,
        "source":      m.source,
        "username":    m.username,
        "image_url":   m.image_url,
        "thumb_url":   m.thumb_url,
        "media_type":  m.media_type,
        "tweet_text":  m.tweet_text,
        "tweet_url":   m.tweet_url,
        "captured_at": m.captured_at.isoformat() if m.captured_at else None,
    }


@router.get("/intel")
async def get_intel_media(limit: int = Query(30, ge=1, le=60)):
    """Return the most recent chart/image captures from analytical sources."""
    async with async_session() as session:
        result = await session.execute(
            select(IntelMedia)
            .order_by(IntelMedia.captured_at.desc())
            .limit(min(limit, 60))
        )
        items = result.scalars().all()
        return {"media": [_media_to_dict(m) for m in items], "total": len(items)}
