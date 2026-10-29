"""Bounded publisher-feed ingestion.

Default free mode publishes attributed source headlines and preserved excerpts as
unclassified, unscored reports. It never calls a model or guesses coordinates.
Optional model mode is explicitly configured and preserves the extraction gates.
Publisher ratings below are inherited editorial priors, not calibrated accuracy.
"""

import asyncio
import copy
from contextlib import asynccontextmanager
from contextvars import ContextVar
from app.services.ingest_ledger import capture_report, finish_report, report_identity
from app.services.evidence import make_report, canonical_url
from app.services.source_catalog import RSS_FEEDS as FEEDS
import os
import hashlib
import logging
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from app.config import settings

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select, text

from app.db import async_session
from app.models import Event, SourceReport
from app.services.anomaly import analyze_anomaly
from app.services.broadcaster import broadcaster
from app.schemas import EventRead, EventWS
from app.services.classifier import classify_message
from app.services.dedup import check_duplicate, merge_duplicate
from app.services.geocoder import geocode

logger = logging.getLogger(__name__)

# ── CONFIG ─────────────────────────────────────────────────────────────────────

POLL_INTERVAL = 300  # seconds between feed polls (5 min)

X_POLL_INTERVAL = 60  # Historical configured interval; provider limits/cost require separate qualification.
X_TWEET_FIELDS  = "created_at,text,author_id,entities,attachments"

# X/Twitter accounts are used only after explicit paid connector opt-in.
# Historical opt-in paid-X watchlist; IDs, account names and prior scores are
# unverified legacy metadata. No current pricing, speed, independence or
# accuracy claims are established. RSS catalog qualification does not qualify X.
X_ACCOUNTS = [{'id': '1499038738562920451', 'username': 'GeoConfirmed', 'source': 'x_geoconfirmed', 'reliability': 5},
 {'id': '1496286557053071361',
  'username': 'OSINTdefender',
  'source': 'x_osintdefender',
  'reliability': 4},
 {'id': '1050478262009262080', 'username': 'AuroraIntel', 'source': 'x_auroraintel', 'reliability': 4},
 {'id': '841694471293173760', 'username': 'ELINTNews', 'source': 'x_elintnews', 'reliability': 4},
 {'id': '1660440916451024897', 'username': 'OSINTWarfare', 'source': 'x_osintwarfare', 'reliability': 4},
 {'id': '1776269230159147008', 'username': 'DropSiteNews', 'source': 'x_dropsitenews', 'reliability': 4},
 {'id': '1212783083272855552', 'username': 'Osint613', 'source': 'x_osint613', 'reliability': 3},
 {'id': '332166927', 'username': 'IntelSky', 'source': 'x_intelsky', 'reliability': 3},
 {'id': '1470610924100734976',
  'username': 'Truthtellerftm',
  'source': 'x_truthteller',
  'reliability': 3},
 {'id': '2032216582542540801',
  'username': 'lourage_america',
  'source': 'x_lourage_america',
  'reliability': 3},
 {'id': '1028770525160660993', 'username': 'IranIntl_En', 'source': 'x_iranintl', 'reliability': 3},
 {'id': '18424289', 'username': 'AJENews', 'source': 'x_ajebreaking', 'reliability': 4},
 {'id': '24506246', 'username': 'haaretzcom', 'source': 'x_haaretz', 'reliability': 3},
 {'id': '328435793', 'username': 'UKMTO', 'source': 'x_ukmto', 'reliability': 5},
 {'id': '556177249', 'username': 'US5thFleet', 'source': 'x_us5thfleet', 'reliability': 2},
 {'id': '230649182', 'username': 'CMF_Bahrain', 'source': 'x_cmf', 'reliability': 2},
 {'id': '784455407486009344',
  'username': 'TankerTrackers',
  'source': 'x_tankertrackers',
  'reliability': 4},
 {'id': '241068113', 'username': 'safety4sea', 'source': 'x_safety4sea', 'reliability': 3},
 {'id': '36442519', 'username': 'chrismartenson', 'source': 'x_chrismartenson', 'reliability': 4},
 {'id': '823766058909761536', 'username': 'LynAldenContact', 'source': 'x_lynalden', 'reliability': 5},
 {'id': '2936015319', 'username': 'LukeGromen', 'source': 'x_lukeGromen', 'reliability': 4},
 {'id': '60783724', 'username': 'ianbremmer', 'source': 'x_ianbremmer', 'reliability': 4},
 {'id': '18178751', 'username': 'MichaelPettis', 'source': 'x_michaelpettis', 'reliability': 5},
 {'id': '2453385626', 'username': 'RaoulGMI', 'source': 'x_raoulpal', 'reliability': 4},
 {'id': '2584103654', 'username': 'TaviCosta', 'source': 'x_tavicosta', 'reliability': 4},
 {'id': '44706837', 'username': 'EurasiaGroup', 'source': 'x_eurasiagroup', 'reliability': 4},
 {'id': '937778257952432128', 'username': 'gzeromedia', 'source': 'x_gzeromedia', 'reliability': 4},
 {'id': '272019676', 'username': 'CSIS', 'source': 'x_csis', 'reliability': 3},
 {'id': '831603050817138688', 'username': 'FreightWaves', 'source': 'x_freightwaves', 'reliability': 4},
 {'id': '1444029422', 'username': 'WarOnTheRocks', 'source': 'x_warontherocks', 'reliability': 4},
 {'id': '16076032', 'username': 'ggreenwald', 'source': 'x_ggreenwald', 'reliability': 4}]

# Per-account since_id cursor — avoids re-processing old tweets on restart
_x_since_ids: dict[str, str] = {}

MIN_SEVERITY = 3

# Historical compatibility constants; unlocated reports use null coordinates.
UNKNOWN_LAT = -25.0
UNKNOWN_LON = 80.0

# ── FEED REGISTRY ──────────────────────────────────────────────────────────────

# ── KEYWORD FILTER ─────────────────────────────────────────────────────────────
# Articles must contain at least one of these terms to be sent to the classifier.
# This avoids burning API credits on unrelated news.

CONFLICT_KEYWORDS = [
    # ── Core theater: Iran-Israel-US ─────────────────────────────────────────
    # Parties
    "iran", "israel", "irgc", "idf", "mossad", "hezbollah", "hamas",
    "houthi", "houthis", "ansar allah", "islamic revolutionary",
    # Conflict terms
    "missile", "strike", "attack", "bomb", "explosion", "airstrike", "air strike",
    "drone", "ballistic", "cruise missile", "rocket", "intercept", "iron dome",
    "kill", "killed", "dead", "casualties", "wounded", "destroyed",
    # Locations
    "tehran", "tel aviv", "haifa", "beirut", "damascus", "baghdad", "sanaa",
    "hormuz", "red sea", "persian gulf", "natanz", "bushehr", "dimona",
    "gaza", "west bank", "golan", "rafah",
    # Nuclear
    "nuclear", "enrichment", "uranium", "centrifuge", "warhead",
    # Military/escalation
    "carrier", "warship", "navy", "troops", "military", "escalation",
    "retaliation", "ceasefire", "war", "combat",
    # US involvement
    "pentagon", "centcom", "camp david",

    # ── Global military incidents ────────────────────────────────────────────
    # High-severity military accidents, crashes, and incidents outside the core
    # theater that our monitored sources flag as significant.
    # These pass the keyword filter but still require severity >= 3 from Claude.
    "plane crash", "aircraft crash", "helicopter crash", "military aircraft",
    "military plane", "transport plane", "military helicopter", "nato",
    "military base", "military convoy", "military vehicle", "military operation",
    "special forces", "commandos", "marines killed", "soldiers killed",
    "troops killed", "military dead", "mass casualty",
    # Major geopolitical actors not in core theater
    "russia", "ukraine", "china", "taiwan", "north korea", "pakistan",
    "india", "india-pakistan", "kashmir",
    # Other escalation signals
    "coup", "assassination", "chemical weapon", "biological weapon",
    "cyber attack", "critical infrastructure", "power grid attack",
    "oil tanker", "cargo ship", "shipping attack", "piracy",
]

def _is_conflict_relevant(title: str, description: str) -> bool:
    """Legacy English substring discovery filter; not a fact or event verdict."""
    combined = f"{title} {description}".lower()
    return any(kw in combined for kw in CONFLICT_KEYWORDS)


# ── SEEN ARTICLE CACHE ─────────────────────────────────────────────────────────
# In-memory set of URL hashes to avoid re-processing on each poll.
# Cleared on restart (acceptable — dedup check in DB handles that).

_seen_hashes: set[str] = set()
_MAX_SEEN = 5000  # prevent unbounded growth


def _article_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _already_seen(url: str) -> bool:
    h = _article_hash(url)
    if h in _seen_hashes:
        return True
    _seen_hashes.add(h)
    if len(_seen_hashes) > _MAX_SEEN:
        # Remove oldest ~500 entries (simple set doesn't track order, just clear half)
        to_remove = list(_seen_hashes)[:500]
        for item in to_remove:
            _seen_hashes.discard(item)
    return False


# ── RSS PARSER ─────────────────────────────────────────────────────────────────

def _parse_rss(xml_text: str | bytes) -> list[dict]:
    """Parse RSS/Atom feed XML and return list of article dicts."""
    articles = []
    try:
        # Strip UTF-8 BOM (\ufeff) and leading whitespace that some feeds
        # (notably xcancel.com/nitter) prepend before the <?xml?> declaration.
        # ElementTree raises "XML or text declaration not at start of entity"
        # if any character precedes the declaration.
        xml_text = (xml_text.removeprefix(b"\xef\xbb\xbf").lstrip(b" \t\r\n")
                    if isinstance(xml_text, bytes) else xml_text.lstrip("\ufeff \t\r\n"))
        root = ElementTree.fromstring(xml_text)
    except (ElementTree.ParseError, DefusedXmlException) as e:
        raise ValueError("Invalid or unsafe feed XML") from e

    # Handle both RSS 2.0 (channel/item) and Atom (feed/entry)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            url = (item.findtext("link") or "").strip()
            pub_date_str = item.findtext("pubDate")
            try:
                pub_date = parsedate_to_datetime(pub_date_str) if pub_date_str else None
            except Exception:
                pub_date = None
            if url:
                if len(articles) >= _MAX_PARSED_ITEMS:
                    raise ValueError("Feed item count exceeds parser limit")
                articles.append({"title": title, "description": desc, "url": url, "published": pub_date})
        return articles

    # Unknown documents are a failed feed, not a healthy empty feed.
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("Unsupported feed document")

    # Atom
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
        def link_priority(link):
            alternate = (link.get("rel") or "alternate").lower() == "alternate"
            kind = (link.get("type") or "").split(";", 1)[0].strip().lower()
            return (0 if alternate and kind in {"text/html", "application/xhtml+xml"}
                    else 1 if alternate and not kind else 2 if alternate else 3)
        links = [link for link in entry.findall("atom:link", ns) if canonical_url(link.get("href") or "")]
        link_el = min(links, key=link_priority) if links else None
        url = (link_el.get("href") if link_el is not None else "") or ""
        published_str = entry.findtext("atom:published", namespaces=ns) or entry.findtext("atom:updated", namespaces=ns)
        try:
            pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00")) if published_str else None
        except Exception:
            pub_date = None
        if url:
            if len(articles) >= _MAX_PARSED_ITEMS:
                raise ValueError("Feed item count exceeds parser limit")
            articles.append({"title": title, "description": summary, "url": url, "published": pub_date,
                "source_time_basis": "source_publication_time" if entry.findtext("atom:published", namespaces=ns) else "source_updated_time"})

    return articles


# ── ARTICLE PROCESSOR ──────────────────────────────────────────────────────────

async def _process_model_article(
    title: str,
    description: str,
    url: str,
    published: datetime | None,
    source_name: str,
    reliability: int,
):
    """Run one article through classify → geocode → save pipeline."""
    # Build the text we'll classify (title + description)
    full_text = f"{title}\n\n{description}".strip()
    if len(full_text) < 20:
        return

    report = {"source": f"rss_{source_name}", "channel_name": source_name, "source_url": url,
              "raw_text": full_text, "timestamp": published.isoformat() if published else None, "time_basis": "source_publication_time" if published else "unknown"}
    receipt, retained, resumed = await _capture_rss_report(report)
    if receipt is None:
        return retained
    if resumed is not None:
        report, full_text = resumed, resumed["raw_text"]
        published, url = _source_clock(report), report["source_url"]

    if published is None or published.tzinfo is None:
        await finish_report(receipt, "undated_source")
        return
    if published > _clock() + timedelta(minutes=5):
        await finish_report(receipt, "future_source_time")
        return "future_source_time"
    if resumed and await _recover_committed_report(report, receipt, "extracted"):
        return "recovered"

    # Classify
    result = await classify_message(full_text)
    if result.get("classification_status", "invalid") != "extracted":
        await finish_report(receipt, result.get("classification_status", "invalid"))
        return
    report["summary"] = result.get("summary", "")
    report["classification_status"] = "extracted"
    severity = result.get("severity", 5)

    # Classifier flagged this as noise/commentary
    if result.get("is_noise"):
        await finish_report(receipt, "noise")
        logger.debug("RSS: noise/commentary dropped: %s", title[:60])
        return

    if severity < MIN_SEVERITY:
        await finish_report(receipt, "below_threshold")
        logger.debug("RSS: low severity (%d) — skipping: %s", severity, title[:60])
        return

    # Geocode
    location_name = result.get("location_name", "Unknown")
    coords = await geocode(location_name)
    if coords:
        lat, lon = coords
        is_geolocated = True
    else:
        lat, lon = None, None
        is_geolocated = False

    geometry = from_shape(Point(lon, lat), srid=4326) if coords else None

    async with async_session() as session:
        # Check for semantic duplicates
        existing = await check_duplicate(
            session,
            result.get("summary", ""),
            result.get("event_type", "military"),
            lat, lon,
            published, source_name=source_name, report=report,
        )
        if existing:
            await merge_duplicate(session, existing, source_name, severity, lat, lon, report=report)
            await finish_report(receipt, "extracted", existing.id)
            ws_payload = EventWS(type="new_event", event=EventRead.model_validate(existing))
            await broadcaster.broadcast(ws_payload.model_dump_json())
            return

        # Check for exact URL duplicate
        result_check = await session.execute(
            select(Event.id).where(Event.source_url == url).limit(1)
        )
        prior_id = result_check.scalar_one_or_none()
        if prior_id is not None:
            await finish_report(receipt, "source_revision_needs_review", prior_id)
            return

        # Anomaly detection for severity 5+
        anomaly_score = 0
        anomaly_analysis = ""
        if severity >= 5:
            try:
                anomaly = await analyze_anomaly(
                    summary=result.get("summary", ""),
                    event_type=result.get("event_type", "military"),
                    severity=severity,
                    location_name=location_name,
                    raw_text=full_text,
                )
                anomaly_score = anomaly.get("anomaly_score", 0)
                anomaly_analysis = anomaly.get("analysis", "")
            except Exception as e:
                logger.warning("Anomaly analysis failed for RSS %s: %s", url[:60], e)

        db_event = Event(
            source=f"rss_{source_name}",
            channel_name=source_name,
            raw_text=full_text,
            summary=result.get("summary", full_text[:200]),
            event_type=result.get("event_type", "military"),
            severity=severity,
            lat=lat,
            lon=lon,
            geometry=geometry,
            timestamp=published,
            source_reliability=reliability,
            location_name=location_name,
            telegram_message_id=None,
            source_url=url,
            reporting_channels=source_name,
            classification_status="extracted",
            geolocation_precision="unknown",
            reports=[make_report(report)],
            anomaly_score=anomaly_score,
            anomaly_analysis=anomaly_analysis,
        )
        session.add(db_event)
        await session.commit()
        await session.refresh(db_event)
        await finish_report(receipt, "extracted", db_event.id)

        ws_payload = EventWS(type="new_event", event=EventRead.model_validate(db_event))
        await broadcaster.broadcast(ws_payload.model_dump_json())
        logger.info(
            "RSS event #%d | sev=%d | loc='%s' -> (%s,%s) | geo=%s | anomaly=%d | %s",
            db_event.id, severity, location_name, lat, lon, is_geolocated, anomaly_score, url[:80],
        )


# ── FREE REPORT PROCESSOR AND FEED HEALTH ─────────────────────────────────────

_feed_health: dict[str, dict] = {}
_cycle_status: dict = {}
_owned_receipt: ContextVar[str | None] = ContextVar("rss_owned_receipt", default=None)
_MAX_PARSED_ITEMS = 1000
_FETCH_CONCURRENCY = 4
_TERMINAL_RECEIPTS = frozenset({
    "reported", "extracted", "source_revision_needs_review", "invalid_source_metadata",
    "input_too_large", "undated_source", "future_source_time", "noise", "below_threshold", "filtered",
})
_RESUMABLE_RECEIPTS = frozenset({
    "received", "pending_receipt", "retryable_error", "provider_error", "unavailable", "disabled", "invalid",
})


def _clock():
    return datetime.now(timezone.utc)


def _iso(stamp):
    return stamp.isoformat() if stamp else None


def _rss_report(title, description, url, published, source_name, *, feed_context=None, model=False):
    full_text = f"{title}\n\n{description}".strip()
    report = {"source": f"rss_{source_name}", "channel_name": source_name,
        "source_url": url if model else canonical_url(url), "raw_text": full_text,
        "timestamp": _iso(published),
        "time_basis": (feed_context or {}).get("source_time_basis", "source_publication_time") if published else "unknown"}
    if not model:
        report.update(classification_status="not_requested", summary=title.strip(),
            processing_mode="publisher_metadata", headline_source="publisher", feed_context=dict(feed_context or {}))
        if len(full_text) > 12000:
            report.update(original_text_sha256=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                raw_text=full_text[:12000], raw_text_truncated=True)
    return report


@asynccontextmanager
async def _receipt_ownership(report):
    """Crash-releasing ownership; never mutate immutable source content or time.

    This separate transaction holds only an advisory lock, so Event/ledger DML
    can commit normally. A hash collision can defer work, never merge reports.
    PostgreSQL releases the lock on transaction/connection/process termination.
    """
    identity, _ = report_identity(report)
    key = int(identity[:16], 16)
    if key >= 2**63:
        key -= 2**64
    async with async_session() as session, session.begin():
        acquired = (await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})).scalar_one()
        token = _owned_receipt.set(identity if acquired else None)
        try:
            yield acquired
        finally:
            _owned_receipt.reset(token)


async def _receipt_status(identity):
    async with async_session() as session:
        result = await session.execute(select(SourceReport.status).where(SourceReport.identity == identity))
        return result.scalar_one_or_none()


async def _receipt_source(identity):
    async with async_session() as session:
        result = await session.execute(select(SourceReport.report).where(SourceReport.identity == identity))
        return copy.deepcopy(result.scalar_one_or_none())


def _source_clock(report):
    value = report.get("timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
    except (ValueError, TypeError, OverflowError):
        return None


async def _capture_rss_report(report):
    created = await capture_report(report)
    if created is not None:
        return created, "received", None
    identity, _ = report_identity(report)
    status = await _receipt_status(identity)
    if status in _TERMINAL_RECEIPTS:
        return None, "duplicate", None
    if status in _RESUMABLE_RECEIPTS and _owned_receipt.get() == identity:
        original = await _receipt_source(identity)
        if not isinstance(original, dict) or report_identity(original)[0] != identity:
            raise ValueError("Stored receipt source identity is invalid")
        return identity, status, original
    # An unknown or active receipt is never declared a terminal duplicate.
    return None, "pending_receipt", None


async def _terminal_identities(reports):
    identities = {report_identity(report)[0] for report in reports}
    if not identities:
        return set()
    async with async_session() as session:
        result = await session.execute(select(SourceReport.identity).where(
            SourceReport.identity.in_(identities), SourceReport.status.in_(_TERMINAL_RECEIPTS)))
        return set(result.scalars().all())


async def _recover_committed_report(report, receipt, status):
    """Repair commit-before-finish only for the same exact source/body/URL."""
    async with async_session() as session:
        existing = (await session.execute(select(Event).where(Event.source_url == report["source_url"]).limit(1))).scalar_one_or_none()
    if existing is None or existing.source != report["source"] or existing.channel_name != report["channel_name"]:
        return False
    _, expected_hash = report_identity(report)
    if hashlib.sha256((existing.raw_text or "").encode("utf-8")).hexdigest() != expected_hash:
        return False
    if existing.timestamp != _source_clock(report):
        return False
    await finish_report(receipt, status, existing.id)
    await broadcaster.broadcast(EventWS(type="new_event", event=EventRead.model_validate(existing)).model_dump_json())
    return True


def configured_feeds() -> list[dict]:
    chosen = {part.strip() for part in settings.rss_sources.split(",") if part.strip()}
    known = {feed["source"] for feed in FEEDS}
    if chosen - known:
        raise ValueError("rss_sources contains an unknown source ID")
    return [feed for feed in FEEDS if feed["source"] in chosen or (not chosen and feed.get("default_enabled", True))]


def get_feed_status() -> dict:
    now = _clock()
    sources = []
    try:
        feeds = configured_feeds()
    except ValueError:
        return {"enabled": settings.live_ingestion_enabled, "mode": settings.rss_processing_mode,
                "status": "misconfigured", "error_type": "UnknownSourceID", "feeds": []}
    for feed in feeds:
        state = dict(_feed_health.get(feed["source"], {}))
        success = state.get("last_success_at")
        publication = state.get("last_published_at")
        age = (now - success).total_seconds() if success else None
        publication_age = (now - publication).total_seconds() if publication else None
        state["status"] = state.get("status", "unavailable")
        if not settings.live_ingestion_enabled:
            state["status"] = "disabled"
        elif state["status"] in {"ok", "empty"} and age is not None and age > max(2 * settings.rss_poll_interval_seconds, 600):
            state["status"] = "stale"
        sources.append({**state, "source": feed["source"], "url": feed["url"],
            "display_name": feed.get("display_name", feed["source"]), "role": feed.get("role", "unassessed"),
            "prior_status": feed.get("prior_status", "unassessed"),
            "last_attempt_at": _iso(state.get("last_attempt_at")), "last_success_at": _iso(success),
            "last_published_at": _iso(publication), "cache_age_seconds": age,
            "last_reported_at": _iso(state.get("last_reported_at")),
            "next_attempt_at": _iso(state.get("next_attempt_at")),
            "publication_age_seconds": publication_age,
            "publication_stale": publication_age is not None and publication_age > 86400,
            "publication_in_future": publication_age is not None and publication_age < -300})
    return {"enabled": settings.live_ingestion_enabled, "mode": settings.rss_processing_mode,
        "relevance_mode": "keywords" if settings.rss_processing_mode == "model" else settings.rss_relevance_mode,
        "configured_relevance_mode": settings.rss_relevance_mode,
        "poll_interval_seconds": settings.rss_poll_interval_seconds, "feeds": sources,
        "cycle": dict(_cycle_status),
        "coverage_limitation": "Selected publishers; unreviewed metadata, not incident verification. Source publication is not incident time. Conditional HTTP is deferred so unfinished feed items cannot disappear behind304 responses."}


get_rss_status = get_feed_status


async def _process_article(title: str, description: str, url: str, published: datetime | None,
                           source_name: str, reliability: int | None, *, feed_context: dict | None = None):
    report = _rss_report(title, description, url, published, source_name,
        feed_context=feed_context, model=settings.rss_processing_mode == "model")
    async with _receipt_ownership(report) as owned:
        if not owned:
            return "pending_receipt"
        try:
            return await _process_article_unlocked(title, description, url, published,
                source_name, reliability, feed_context=feed_context)
        except asyncio.CancelledError:
            # No durable processing lease is stored. A received/pending receipt
            # remains resumable after the advisory transaction is released.
            raise
        except Exception:
            identity, _ = report_identity(report)
            try:
                if await _receipt_status(identity) not in _TERMINAL_RECEIPTS:
                    await finish_report(identity, "retryable_error")
            except Exception as error:
                logger.warning("RSS retry state could not be persisted (%s)", type(error).__name__)
            raise


async def _process_article_unlocked(title: str, description: str, url: str, published: datetime | None,
                           source_name: str, reliability: int | None, *, feed_context: dict | None = None):
    if settings.rss_processing_mode == "model":
        return await _process_model_article(title, description, url, published, source_name, reliability)
    # Publisher-authored metadata is preserved verbatim; it is not a model summary.
    full_text = f"{title}\n\n{description}".strip()
    report = _rss_report(title, description, url, published, source_name, feed_context=feed_context)
    receipt, retained, resumed = await _capture_rss_report(report)
    if receipt is None:
        return retained
    if resumed is not None:
        report, full_text = resumed, resumed["raw_text"]
        title, published = resumed.get("summary", ""), _source_clock(resumed)
    if not title.strip() or not report["source_url"]:
        await finish_report(receipt, "invalid_source_metadata")
        return "invalid_source_metadata"
    if report.get("raw_text_truncated"):
        await finish_report(receipt, "input_too_large")
        return "input_too_large"
    if published is None or published.tzinfo is None:
        await finish_report(receipt, "undated_source")
        return "undated_source"
    if published > _clock() + timedelta(minutes=5):
        await finish_report(receipt, "future_source_time")
        return "future_source_time"
    if resumed and await _recover_committed_report(report, receipt, "reported"):
        return "recovered"
    async with async_session() as session:
        existing = await session.execute(select(Event.id).where(
            Event.source_url == report["source_url"]).limit(1))
        prior_id = existing.scalar_one_or_none()
        if prior_id is not None:
            await finish_report(receipt, "source_revision_needs_review", prior_id)
            return "source_revision_needs_review"
        event = Event(source=report["source"], channel_name=source_name, raw_text=full_text,
            summary=title.strip(), event_type="unclassified", severity=0,
            lat=None, lon=None, geometry=None, timestamp=published,
            source_reliability=reliability, location_name="", source_url=report["source_url"],
            report_count=1, reporting_channels=source_name, confirmed_networks="",
            classification_status="not_requested", geolocation_precision="unknown",
            reports=[{**make_report(report), "feed_context": report["feed_context"]}], anomaly_score=0, anomaly_analysis="")
        session.add(event)
        await session.commit()
        await session.refresh(event)
        await finish_report(receipt, "reported", event.id)
        await broadcaster.broadcast(EventWS(type="new_event", event=EventRead.model_validate(event)).model_dump_json())
    return "reported"


async def _read_feed_response(feed: dict, client: httpx.AsyncClient):
    # Streaming caps decompressed bytes, including falsely declared/absent lengths.
    limit = settings.rss_max_response_bytes
    async with asyncio.timeout(30), client.stream("GET", feed["url"], timeout=15, follow_redirects=True) as response:
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > limit:
            raise ValueError("Feed response exceeds configured byte limit")
        content = bytearray()
        async for block in response.aiter_bytes(chunk_size=16384):
            if len(content) + len(block) > limit:
                raise ValueError("Feed response exceeds configured byte limit")
            content.extend(block)
        return bytes(content), {"http_status": response.status_code,
            "content_type": response.headers.get("content-type", "")[:120],
            "etag_present": bool(response.headers.get("etag")),
            "last_modified_present": bool(response.headers.get("last-modified")),
            "redirects": len(response.history)}


async def _read_feed_bytes(feed: dict, client: httpx.AsyncClient) -> bytes:
    return (await _read_feed_response(feed, client))[0]


def _retry_seconds(error, failures):
    base = min(settings.rss_poll_interval_seconds * 2 ** min(failures - 1, 6), 3600)
    raw = error.response.headers.get("retry-after", "") if isinstance(error, httpx.HTTPStatusError) else ""
    if raw:
        try:
            requested = float(raw)
        except ValueError:
            try:
                stamp = parsedate_to_datetime(raw)
                requested = (stamp - _clock()).total_seconds() if stamp.tzinfo else 0
            except (ValueError, TypeError, OverflowError):
                requested = 0
        if requested == requested and requested > 0:
            base = max(base, min(requested, 3600))
    return max(1, min(base, 3600))


async def _fetch_feed(feed, http_client):
    source = feed["source"]
    state = _feed_health.setdefault(source, {})
    state.update(attempted_items=0, published_items=0, rejected_items=0,
        skipped_terminal_items=0, recovered_items=0, pending_items=0,
        outcome_counts={}, ingest_error_type=None)
    if state.get("next_attempt_at") and state["next_attempt_at"] > _clock():
        state["backoff_active"] = True
        return None
    begin = time.monotonic()
    state.update(last_attempt_at=_clock(), attempted_items=0, published_items=0,
        rejected_items=0, skipped_terminal_items=0, recovered_items=0,
        ingest_error_type=None, error_type=None, backoff_active=False)
    try:
        content, response_meta = await _read_feed_response(feed, http_client)
        articles = _parse_rss(content)
        state.update(response_meta)
        state["parsed_items"] = len(articles)
        dated = [item["published"] for item in articles if item.get("published") and item["published"].tzinfo is not None]
        state["last_published_at"] = max(dated) if dated else None
        state.update(last_success_at=_clock(), status="ok" if articles else "empty",
            consecutive_failures=0, next_attempt_at=None)
        # Undated and future clocks stay in the queue for explicit retained
        # receipts; newest dated items are considered first, never dated as now.
        articles.sort(key=lambda row: row["published"].timestamp()
            if row.get("published") and row["published"].tzinfo else float("-inf"), reverse=True)
        return articles, {"feed_url": feed["url"], "feed_content_sha256": hashlib.sha256(content).hexdigest(),
            "retrieved_at": _iso(state["last_success_at"]),
            "source_role": feed.get("role", "unassessed"), "prior_status": feed.get("prior_status", "unassessed")}
    except asyncio.CancelledError:
        raise
    except Exception as error:
        failures = min(state.get("consecutive_failures", 0) + 1, 20)
        state.update(status="failed", error_type=type(error).__name__, consecutive_failures=failures,
            next_attempt_at=_clock() + timedelta(seconds=_retry_seconds(error, failures)))
        if isinstance(error, httpx.HTTPStatusError):
            state["http_status"] = error.response.status_code
        logger.warning("RSS %s fetch failed (%s); retaining prior clocks", source, type(error).__name__)
        return None
    finally:
        state["fetch_seconds"] = round(time.monotonic() - begin, 6)


async def _poll_feed(feed: dict, http_client: httpx.AsyncClient, max_items: int | None = None,
                     *, fetch_semaphore=None, processing_lock=None) -> int:
    source = feed["source"]
    state = _feed_health.setdefault(source, {})
    budget = min(settings.rss_max_items_per_feed, max_items if max_items is not None else settings.rss_max_items_per_feed)
    state["attempt_quota"] = budget
    if fetch_semaphore is None:
        fetched = await _fetch_feed(feed, http_client)
    else:
        async with fetch_semaphore:
            fetched = await _fetch_feed(feed, http_client)
    if fetched is None or budget <= 0:
        return 0
    articles, context = fetched
    try:
        selected = [article for article in articles if
            (settings.rss_processing_mode == "reports" and settings.rss_relevance_mode == "selected_sources")
            or _is_conflict_relevant(article["title"], article["description"])]
        reports = [_rss_report(article["title"], article["description"], article["url"], article["published"], source,
            feed_context=context, model=settings.rss_processing_mode == "model") for article in selected]
        terminal = await _terminal_identities(reports)
        for article, report in zip(selected, reports):
            if state["attempted_items"] >= budget:
                break
            if report_identity(report)[0] in terminal:
                state["skipped_terminal_items"] += 1
                continue
            async def process():
                state["attempted_items"] += 1
                return await _process_article(article["title"], article["description"], article["url"],
                    article["published"], source, feed["reliability"],
                    feed_context={**context, "source_time_basis": article.get("source_time_basis", "source_publication_time")})
            if processing_lock is None:
                outcome = await process()
            else:
                async with processing_lock:
                    outcome = await process()
            if outcome == "reported":
                state["published_items"] += 1
                state["last_reported_at"] = _clock()
            elif outcome == "recovered":
                state["recovered_items"] += 1
            elif outcome == "pending_receipt":
                state["pending_items"] += 1
            elif outcome not in {None, "duplicate"}:
                state["rejected_items"] += 1
            label = outcome or "legacy_model_completion"
            state["outcome_counts"][label] = state["outcome_counts"].get(label, 0) + 1
        return state["attempted_items"]
    except asyncio.CancelledError:
        raise
    except Exception as error:
        state["ingest_error_type"] = type(error).__name__
        state.update(status="degraded", error_type=type(error).__name__)
        logger.warning("RSS %s ingest failed (%s); retrieval clock is separate", source, type(error).__name__)
        return state["attempted_items"]


# ── X / TWITTER API v2 POLLER ──────────────────────────────────────────────────

async def _poll_x_account(account: dict, http_client: httpx.AsyncClient, bearer: str):
    """Fetch latest tweets for one X account via API v2 and run them through the pipeline."""
    uid      = account["id"]
    username = account["username"]
    source   = account["source"]
    rel      = account["reliability"]

    # Analytical sources (ANALYSIS network) get media capture
    ANALYSIS_SOURCES = {
        "x_chrismartenson","x_lynalden","x_lukeGromen","x_ianbremmer",
        "x_michaelpettis","x_raoulpal","x_tavicosta","x_eurasiagroup",
        "x_gzeromedia","x_csis","x_freightwaves","x_warontherocks","x_ggreenwald",
    }
    want_media = source in ANALYSIS_SOURCES

    params: dict = {
        "max_results": 10,
        "tweet.fields": X_TWEET_FIELDS,
        "expansions": "author_id,attachments.media_keys" if want_media else "author_id",
    }
    if want_media:
        params["media.fields"] = "url,preview_image_url,type,width,height"
    since = _x_since_ids.get(uid)
    if since:
        params["since_id"] = since

    url = f"https://api.twitter.com/2/users/{uid}/tweets"
    try:
        resp = await http_client.get(
            url, params=params,
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=15,
        )
    except Exception as e:
        logger.warning("X API fetch failed for @%s: %s", username, e)
        return

    if resp.status_code == 429:
        logger.warning("X API rate-limited on @%s — will retry next cycle", username)
        return
    if resp.status_code != 200:
        logger.warning("X API @%s returned HTTP %d: %s", username, resp.status_code, resp.text[:120])
        return

    data = resp.json()
    tweets = data.get("data", [])

    # Log X API usage — v2 pay-per-use charges per tweet returned ($0.10 per 100 tweets)
    if tweets:
        try:
            from app.db import async_session as _async_session
            from sqlalchemy import text as _text
            _tc = len(tweets)
            _cost = _tc * 0.001  # $0.001 per tweet
            async with _async_session() as _s:
                await _s.execute(_text(
                    "INSERT INTO usage_log (operation, model, input_tokens, output_tokens, cost_usd, meta) "
                    "VALUES (:op, :model, :inp, :out, :cost, CAST(:meta AS jsonb))"
                ), {"op": "x_poll", "model": "x-api-v2",
                    "inp": _tc, "out": 0, "cost": _cost,
                    "meta": f'{{"account":"{username}"}}' })
                await _s.commit()
        except Exception as _le:
            logger.debug("usage_log x_poll: %s", _le)

    if not tweets:
        return

    # Update cursor to newest tweet ID so next poll only gets newer content
    _x_since_ids[uid] = tweets[0]["id"]

    # Build media lookup: media_key → media object
    media_lookup: dict = {}
    if want_media:
        for m in data.get("includes", {}).get("media", []):
            media_lookup[m["media_key"]] = m

    new_count = 0
    media_count = 0
    for tweet in reversed(tweets):   # process oldest-first for correct ordering
        text = tweet.get("text", "").strip()
        if not text or len(text) < 20:
            continue

        tweet_id  = tweet["id"]
        tweet_url = f"https://x.com/{username}/status/{tweet_id}"

        # Parse creation timestamp
        created_str = tweet.get("created_at", "")
        try:
            published = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except Exception:
            published = None

        # ── Media capture for analytical accounts (BEFORE relevance filter) ──
        # Only capture data visuals: charts, graphs, maps, tables — NOT photos of
        # people talking, human-interest stories, pets, etc.
        def _is_data_visual(txt: str) -> bool:
            txt_l = txt.lower()
            # Hard reject: personal/human-interest signals
            reject_patterns = [
                # Personal/human-interest
                "i lie to myself", "broken us financially", "sniffing dog",
                "dog's nose", "dog nose", "woke up", "she's going to wake",
                "prayers", "condolen", "rest in peace", "accident has literally",
                "going to wake up", "awareness", "accountability",
                "dalilah", "trucking safety", "save a life",
                # Non-conflict freight/logistics noise
                "freight fraud", "fraud girl", "booking freight", "fuel surcharge",
                "rock & roll hall", "symposium", "morning minute",
                "ups retrac", "usps plan", "port infrastructure",
                "black hole of the supply chain", "what the truck",
                "malcolm harris", "danielle spinelli", "checklist of do",
                # Crypto/unrelated finance
                "crypto", "bitcoin", "nft", "defi", "web3", "blockchain",
                # Generic domestic politics noise
                "midterms", "cultural cul-de-sac", "democrats", "republicans",
                "ai to drive inclusion",
            ]
            if any(p in txt_l for p in reject_patterns):
                return False
            # Accept: strong data/visual signals
            accept_patterns = [
                "chart", "graph", "data ", "gdp", "inflation", "cpi", "pce",
                "yield", "spread", "rate%", "rates", "index", " %", "basis point",
                "supply chain", "freight rate", "tonnage", "commodity", "oil price",
                "gold", "debt", "deficit", "surplus", "trade balance", "export",
                "import", "market cap", "equity", "bonds", "treasury", "fed ",
                "central bank", "monetary", "fiscal", "geopolit", "sanctions",
                "embargo", "energy", "lng", "brent", "wti", "freight", "shipping",
                "container", "tanker", "map", "region", "territory", "conflict zone",
                "escalat", "military", "strategic", "nuclear", "missile", "drone",
                "casualties", "forces", "troops", "offensive", "defensive",
                "wealth", "income", "wages", "employment", "unemployment",
                "poverty", "food security", "hunger", "famine", "water scarcity",
                "infrastructure", "power grid", "pipeline", "port",
                "forecast", "projection", "outlook", "scenario", "model",
                "historical", "since 19", "since 20", "per year", "per quarter",
                "billion", "trillion", "million", "year-over-year", "yoy", "qoq",
                "global", "world", "emerging market", "developing", "developed",
            ]
            return any(p in txt_l for p in accept_patterns)

        if want_media and tweet.get("attachments", {}).get("media_keys") and _is_data_visual(text):
            from app.models import IntelMedia
            from app.db import async_session as _async_session
            tweet_url_str = f"https://x.com/{username}/status/{tweet_id}"
            for mk in tweet.get("attachments", {}).get("media_keys", []):
                m = media_lookup.get(mk)
                if not m:
                    continue
                img_url   = m.get("url") or m.get("preview_image_url") or ""
                thumb_url = m.get("preview_image_url") or img_url
                if not img_url:
                    continue
                try:
                    async with _async_session() as _sess:
                        from sqlalchemy import select as _select
                        exists = await _sess.execute(
                            _select(IntelMedia.id).where(IntelMedia.tweet_id == tweet_id)
                        )
                        if exists.scalar_one_or_none() is None:
                            _sess.add(IntelMedia(
                                tweet_id   = tweet_id,
                                source     = source,
                                username   = username,
                                image_url  = img_url,
                                thumb_url  = thumb_url,
                                media_type = m.get("type", "photo"),
                                tweet_text = text[:280],
                                tweet_url  = tweet_url_str,
                            ))
                            await _sess.commit()
                            media_count += 1
                            logger.info("intel_media: captured chart @%s tweet=%s", username, tweet_id)
                except Exception as _me:
                    logger.warning("intel_media store error: %s", _me)

        # Skip if already seen by URL (events feed dedup)
        # Content revisions are handled by the durable ingestion ledger.

        # Skip @-reply tweets — these are reactions to other accounts, not original reports.
        # A tweet starting with "@" is always a direct reply (X/Twitter convention).
        # These are noise: they trigger keyword matches on @-handles like "@SecWar" -> "war",
        # and they carry the replying account's opinion rather than a verifiable event.
        if text.lstrip().startswith("@"):
            logger.debug("X @%s: skipping @-reply: %s", username, text[:60])
            continue

        # Only add to events feed if conflict-relevant
        if not _is_conflict_relevant(text, ""):
            continue

        await _process_article(
            title=text[:200],
            description=text,
            url=tweet_url,
            published=published,
            source_name=f"x_{username.lower()}",  # normalise to rss_x_{username} prefix
            reliability=rel,
        )
        new_count += 1
        await asyncio.sleep(0.5)

    if new_count:
        logger.info("X @%s: processed %d relevant tweets", username, new_count)
    if media_count:
        logger.info("X @%s: stored %d chart images in intel_media", username, media_count)


async def start_x_poller():
    """Poll X/Twitter API v2 for OSINT accounts. Runs as a separate background task."""
    if (settings.demo_mode or not settings.live_ingestion_enabled or
            not settings.x_ingestion_enabled or not settings.anthropic_api_key):
        return
    bearer = os.environ.get("TWITTER_BEARER_TOKEN", "").strip()
    if not bearer:
        logger.warning("TWITTER_BEARER_TOKEN not set — X feed poller disabled")
        return

    logger.info("X feed poller starting — monitoring %d accounts", len(X_ACCOUNTS))

    async with httpx.AsyncClient() as http_client:
        while True:
            for account in X_ACCOUNTS:
                try:
                    await _poll_x_account(account, http_client, bearer)
                except Exception as e:
                    logger.exception("Unhandled error polling X @%s: %s", account["username"], e)
                await asyncio.sleep(3)   # small gap between accounts

            logger.debug("X poll cycle complete — sleeping %ds", X_POLL_INTERVAL)
            await asyncio.sleep(X_POLL_INTERVAL)

# ── BACKGROUND TASK ENTRYPOINT ─────────────────────────────────────────────────

_poll_cursor = 0


def _feed_quotas(count, per_feed, global_limit):
    """Reserve each feed's share independently of speed and duplicate volume.

    Unused quota is not borrowed within a cycle. This deliberately favors simple
    strict limits over opportunistic throughput under tiny custom budgets.
    """
    quotas = [0] * count
    remaining = min(global_limit, count * per_feed)
    for _ in range(per_feed):
        for index in range(count):
            if remaining <= 0:
                return quotas
            quotas[index] += 1
            remaining -= 1
    return quotas


async def poll_news_once() -> dict:
    global _poll_cursor
    headers = {"User-Agent": "ConflictMonitor/0.2 (self-hosted source monitor)",
               "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
    feeds = configured_feeds()
    ordered = feeds[_poll_cursor:] + feeds[:_poll_cursor]
    quotas = _feed_quotas(len(ordered), settings.rss_max_items_per_feed, settings.rss_max_ingest_per_cycle)
    begin = time.monotonic()
    _cycle_status.update(started_at=_iso(_clock()), finished_at=None,
        configured_sources=len(ordered), fetch_concurrency=_FETCH_CONCURRENCY,
        reserved_attempts=sum(quotas), attempt_limit=settings.rss_max_ingest_per_cycle,
        attempted_items=0, conditional_http_enabled=False,
        budget_scope="Processing/classifier invocations only; legacy provider retries are not an HTTP/token/dollar cap.")
    fetch_semaphore, processing_lock = asyncio.Semaphore(_FETCH_CONCURRENCY), asyncio.Lock()
    async with httpx.AsyncClient(headers=headers, trust_env=False) as client:
        tasks = [asyncio.create_task(_poll_feed(feed, client, max_items=quota,
            fetch_semaphore=fetch_semaphore, processing_lock=processing_lock))
            for feed, quota in zip(ordered, quotas)]
        try:
            attempts = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    _cycle_status.update(finished_at=_iso(_clock()), seconds=round(time.monotonic() - begin, 6),
        attempted_items=sum(attempts),
        classifier_invocations_upper_bound=sum(attempts) if settings.rss_processing_mode == "model" else 0)
    if feeds:
        _poll_cursor = (_poll_cursor + 1) % len(feeds)
    return get_feed_status()


async def start_news_feed_poller():
    """Configured public RSS feeds; no model or paid API in default report mode."""
    if settings.demo_mode or not settings.live_ingestion_enabled:
        return
    logger.info("RSS report poller: %d configured sources, mode=%s", len(configured_feeds()), settings.rss_processing_mode)
    while True:
        begin = time.monotonic()
        await poll_news_once()
        await asyncio.sleep(max(1, settings.rss_poll_interval_seconds - (time.monotonic() - begin)))
