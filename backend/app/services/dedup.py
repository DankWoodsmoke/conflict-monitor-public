"""Conservative report clustering with retained provenance.

Clustering is a navigation convenience, never independent confirmation. Missing
coordinates, polarity differences, and broad temporal similarity do not auto-merge.
"""
import logging
import re
from datetime import timedelta

from sqlalchemy import and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_DWithin

from app.models import Event
from app.services.evidence import (
    append_report, canonical_source, compatible_claims, make_report,
    parse_channels, report_count, valid_coordinates,
)
from app.services.verification import compute_confirmed_networks

logger = logging.getLogger(__name__)


def _normalize(text: str) -> set[str]:
    return {w for w in re.sub(r"[^\w\s]", "", text.lower()).split() if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def safe_text_match(summary: str, candidate: str) -> bool:
    """A high-precision lexical candidate guard; not proof of semantic identity."""
    a, b = _normalize(summary), _normalize(candidate)
    return (len(a) >= 8 and len(b) >= 8 and compatible_claims(summary, candidate)
            and _jaccard(a, b) >= 0.92)


async def _query_candidates(session, event_type, ts_min, ts_max, lat, lon) -> list[Event]:
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point
    if not valid_coordinates(lat, lon):
        return []
    geom = from_shape(Point(lon, lat), srid=4326)
    stmt = select(Event).where(and_(
        Event.event_type == event_type, Event.timestamp >= ts_min,
        Event.timestamp <= ts_max, Event.report_count > 0,
        ST_DWithin(cast(Event.geometry, Geography), cast(geom, Geography), 2000),
    )).order_by(Event.timestamp.desc(), Event.id.desc()).limit(40)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def check_duplicate(session: AsyncSession, summary: str, event_type: str,
                          lat: float | None, lon: float | None, timestamp,
                          source_name: str = "", report: dict | None = None) -> Event | None:
    # An exact source URL is an addressable replay, even when geolocation failed.
    # Source identity is scoped: equal message IDs on different channels differ.
    if report and report.get("source_url"):
        result = await session.execute(select(Event).where(
            Event.source_url == report["source_url"], Event.report_count > 0,
        ).order_by(Event.id.asc()).limit(2))
        for candidate in result.scalars().all():
            if canonical_source(candidate.channel_name or candidate.source) == canonical_source(source_name):
                incoming = report if report.get("content_sha256") else make_report(report)
                retained = [r if r.get("content_sha256") else make_report(r)
                            for r in (getattr(candidate, "reports", None) or [make_report(candidate)])]
                if any(r["content_sha256"] == incoming["content_sha256"] for r in retained):
                    return candidate
                # A changed article may retract or correct the previous claim.
                # Let the ingestion revision gate retain it for review.
                return None
    if timestamp is None or not valid_coordinates(lat, lon):
        return None
    candidates = await _query_candidates(session, event_type, timestamp - timedelta(minutes=15),
                                         timestamp + timedelta(minutes=15), lat, lon)
    compatible = [c for c in candidates if safe_text_match(summary, c.summary)]
    if not compatible:
        return None
    return max(compatible, key=lambda c: (_jaccard(_normalize(summary), _normalize(c.summary)), -c.id))


async def merge_duplicate(session: AsyncSession, existing: Event, new_channel: str,
                          new_severity: int, new_lat: float | None,
                          new_lon: float | None, report: dict | None = None,
                          *, commit: bool = True):
    """Append source evidence without promoting certainty or changing location.

    Callers should supply the raw report. Without it, retain only the channel label
    and do not manufacture a report identity or increment the count.
    """
    channels = set(parse_channels(existing.reporting_channels or existing.channel_name))
    if new_channel:
        channels.add(canonical_source(new_channel))
    existing.reporting_channels = ", ".join(sorted(channels))
    reports = [r if r.get("report_id") else make_report(r)
               for r in (getattr(existing, "reports", None) or [])]
    if not reports:
        reports = [make_report(existing)]
    if report:
        if not report.get("report_id"):
            report = make_report(report)
        reports = append_report(reports, report)
    existing.reports = reports
    existing.report_count = max(1, report_count(reports))
    # Source-reliability is an editorial prior, not report confidence.
    # Repeats and a more alarming report cannot raise it or replace coordinates.
    existing.confirmed_networks = ", ".join(compute_confirmed_networks(existing.reporting_channels))
    if commit:
        await session.commit()
        await session.refresh(existing)
    logger.info("Cluster #%d: %d retained report identities, %d source labels; verification unassessed",
                existing.id, existing.report_count, len(channels))
