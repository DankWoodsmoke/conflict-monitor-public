"""Conflict Monitor API. Startup never implicitly enables live collection."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.config import settings
from app.db import engine, async_session
from app.security import require_admin_key
from app.public_access import public_capabilities, public_http_denial
from app.database_policy import PUBLIC_REPORT_TABLES
from app.services.runtime import runtime
from app.routes.channels import router as channels_router
from app.routes.events import router as events_router
from app.routes.event_delivery import router as event_delivery_router
from app.routes.tracking import router as tracking_router
from app.routes.ws import router as ws_router
from app.routes.market import router as market_router
from app.routes.sitreps import router as sitreps_router
from app.routes.media import router as media_router
from app.routes.costs import router as costs_router
from app.routes.history import router as history_router
from app.routes.briefing import router as briefing_router
from app.routes.report_analysis import router as report_analysis_router
from app.services.event_delivery import delivery_status, start_event_delivery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("conflict-monitor")
OPTIONAL_JOB_NAMES = {"manual_sitrep", "manual_firms", "local_analysis", "local_video", "sitrep_video", "location_review", "telegram_backfill"}
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.routes.market import start_market, stop_market
    from app.services.broadcaster import broadcaster
    try:
        start_market()
        broadcaster.start()
        # Schema changes are an explicit Alembic operation, never swallowed at startup.
        if settings.demo_mode and not settings.public_read_only:
            from app.services.demo import seed_demo_history, start_demo_event_generator, start_demo_aircraft_poller, start_demo_vessel_poller
            await seed_demo_history(300)
            runtime.start("demo_events", start_demo_event_generator())
            runtime.start("demo_aircraft", start_demo_aircraft_poller())
            runtime.start("demo_vessels", start_demo_vessel_poller())
        elif settings.live_ingestion_enabled and not settings.public_read_only:
            from app.services.telegram import start_telegram_listener
            from app.services.opensky import start_opensky_poller
            from app.services.maritime import start_maritime_poller
            from app.services.satellites import start_tle_fetcher
            from app.services.news_feeds import start_news_feed_poller, start_x_poller
            from app.services.snapshots import start_snapshot_recorder
            from app.services.retro_matcher import start_retro_matcher
            from app.services.satellite_firms import start_firms_poller
            if settings.telegram_transport == "bot":
                from app.services.telegram_bot import start_bot_listener
                runtime.start("telegram", start_bot_listener())
            elif (settings.telegram_transport == "session" and settings.telegram_api_id
                    and settings.telegram_api_hash and settings.telegram_session and settings.telegram_channels):
                runtime.start("telegram", start_telegram_listener())
            runtime.start("aircraft", start_opensky_poller())
            runtime.start("satellites", start_tle_fetcher())
            if settings.aisstream_api_key:
                runtime.start("maritime", start_maritime_poller())
            runtime.start("rss", start_news_feed_poller())
            from app.services.source_digest import start_source_digest
            runtime.start("source_digest", start_source_digest())
            if settings.x_ingestion_enabled and settings.anthropic_api_key:
                runtime.start("x", start_x_poller())
            runtime.start("snapshots", start_snapshot_recorder())
            runtime.start("match_review", start_retro_matcher())
            if settings.firms_map_key:
                runtime.start("thermal_observations", start_firms_poller())
            if settings.public_observation_publisher_enabled:
                from app.services.public_observations import start_public_observation_publisher
                runtime.start("public_observations", start_public_observation_publisher())
            if settings.public_aircraft_publisher_enabled:
                from app.services.public_aircraft import start_public_aircraft_publisher
                runtime.start("public_aircraft", start_public_aircraft_publisher())
            if settings.enable_sitrep_generation and settings.anthropic_api_key:
                from app.services.sitrep_generator import start_sitrep_generator
                runtime.start("sitreps", start_sitrep_generator())
        # Pending publication must resume even if collectors are disabled.
        if not settings.public_read_only:
            runtime.start("event_delivery", start_event_delivery())
        yield
    finally:
        from app.services.classifier import stop_classifier
        # Startup can fail after earlier resources have started. Release every
        # owned resource even if one cleanup operation fails, in dependency order.
        for stop in (runtime.stop, stop_market, stop_classifier, broadcaster.stop, engine.dispose):
            try:
                await stop()
            except Exception as exc:
                logger.warning("Resource cleanup failed (%s)", type(exc).__name__)



app = FastAPI(title="Conflict Monitor", version="0.2.0-rc.5", lifespan=lifespan)
origins = [s.strip() for s in settings.cors_origins.split(",") if s.strip()] or [
    "http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-Admin-Key"])
for router in (channels_router, event_delivery_router, events_router, tracking_router, ws_router,
               market_router, sitreps_router, media_router, costs_router, briefing_router, history_router, report_analysis_router):
    app.include_router(router)


@app.middleware("http")
async def response_headers(request, call_next):
    method = request.method
    if method == "OPTIONS":
        method = request.headers.get("access-control-request-method", "")
    denial = public_http_denial(method, request.url.path)
    response = JSONResponse({"detail": denial[1]}, status_code=denial[0]) if denial else await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def root():
    return {"service": "conflict-monitor", "version": app.version}


@app.get("/health")
async def health():
    try:
        async with async_session() as session:
            tables = sorted(PUBLIC_REPORT_TABLES) if settings.public_read_only else ("events", "source_reports", "source_report_retries", "sitreps", "intel_media",
                          "usage_log", "cost_config", "tracking_snapshots", "channel_checkpoints",
                          "telegram_backfill_jobs", "telegram_backfill_items", "event_delivery_state",
                          "event_deliveries")
            for table in tables:
                await session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        optional_failures = {name: error for name, error in runtime.failures.items() if name in OPTIONAL_JOB_NAMES}
        failed = (any(name not in OPTIONAL_JOB_NAMES for name in runtime.failures)
                  or delivery_status()["status"] == "retrying")
        if settings.public_read_only:
            return JSONResponse({"status": "degraded" if failed else "healthy"}, status_code=503 if failed else 200)
        return JSONResponse({"status": "degraded" if failed else "healthy",
            "database": "connected", "live_ingestion_enabled": settings.live_ingestion_enabled,
            "optional_job_failures": optional_failures,
            "provider_health": "see /status; task liveness does not establish data freshness"},
            status_code=503 if failed else 200)
    except Exception:
        return JSONResponse({"status": "unavailable", **({} if settings.public_read_only else {"database": "unavailable_or_schema_missing"})}, status_code=503)


@app.get("/status")
async def status():
    if settings.public_read_only:
        return {"mode": "public_read_only", **public_capabilities(),
                "limitations": ["Publication approval is separate from collection and factual verification.",
                                "Unavailable layers are withheld, not evidence of no activity."]}
    from app.services.satellites import get_tle_status
    from app.services.opensky import get_aircraft_status
    from app.services.maritime import get_maritime_status
    from app.services.news_feeds import get_feed_status
    from app.services.satellite_firms import get_firms_status
    from app.services.telegram import get_telegram_status
    from app.services.classifier import get_classification_status
    return {**runtime.snapshot(), "mode": "synthetic" if settings.demo_mode else
        "live" if settings.live_ingestion_enabled else "collection_disabled",
        "satellites": get_tle_status(),
        "aircraft": get_aircraft_status(),
        "maritime": get_maritime_status(),
        "news_feeds": get_feed_status(),
        "thermal_observations": get_firms_status(),
        "telegram": get_telegram_status(),
        "event_delivery": delivery_status(),
        "classification": get_classification_status(),
        "limitations": ["Provider freshness does not establish report truth or completeness.",
                        "Source diversity is not independent corroboration."]}


@app.get("/config")
async def config():
    return {"demo_mode": settings.demo_mode and not settings.public_read_only,
        **public_capabilities(),
        "live_ingestion_enabled": settings.live_ingestion_enabled and not settings.public_read_only,
        "generation_enabled": settings.enable_sitrep_generation and not settings.public_read_only,
        "video_generation_enabled": settings.enable_video_generation and not settings.public_read_only,
        "local_ai_enabled": settings.enable_local_ai and not settings.public_read_only,
        "rss_processing_mode": settings.rss_processing_mode,
        "google_earth_enabled": settings.google_earth_enabled and bool(settings.google_maps_browser_key),
        "google_maps_browser_key": settings.google_maps_browser_key if settings.google_earth_enabled else "",
        "sentinel_hub_instance_id": settings.sentinel_hub_instance_id if not settings.public_read_only else "",
        "version": app.version, "conflict_start_date": settings.conflict_start_date}


@app.get("/satellite/hotspots")
async def satellite_hotspots():
    from app.services.satellite_firms import get_last_hotspots
    return get_last_hotspots()


@app.get("/publication/observations")
@app.head("/publication/observations", include_in_schema=False)
@app.get("/publication/observations/download")
@app.head("/publication/observations/download", include_in_schema=False)
@app.get("/publication/observations/download/{batch_id}")
@app.head("/publication/observations/download/{batch_id}", include_in_schema=False)
async def public_observations(request: Request, batch_id: str | None = None):
    from app.services.public_observations import read_public_observations
    if request.query_params:
        raise HTTPException(status_code=400, detail="Publication query parameters are not supported")
    if batch_id is not None:
        import re
        if not re.fullmatch(r"[0-9a-f]{64}", batch_id):
            raise HTTPException(status_code=404)
    try:
        download = "/download" in request.url.path
        data = await read_public_observations(download=download, batch_id=batch_id)
        if data is None:
            return JSONResponse({"status": "expired_or_unavailable", "detail": "This exact publication is unavailable; no newer batch is substituted"}, status_code=410)
        headers = {"Content-Disposition": 'attachment; filename="nasa-firms-publication.json"'} if download else {}
        return JSONResponse(data, headers=headers)
    except Exception:
        return JSONResponse({"status": "unavailable", "detail": "Publication unavailable; coverage is unknown"}, status_code=503)


@app.get("/publication/aircraft")
@app.head("/publication/aircraft", include_in_schema=False)
@app.get("/publication/aircraft/download/{batch_id}")
@app.head("/publication/aircraft/download/{batch_id}", include_in_schema=False)
async def public_aircraft(request: Request, batch_id: str | None = None):
    from app.services.public_aircraft import read_public_aircraft
    if request.query_params:
        raise HTTPException(status_code=400, detail="Publication query parameters are not supported")
    if batch_id is not None:
        import re
        if not re.fullmatch(r"[0-9a-f]{64}", batch_id):
            raise HTTPException(status_code=404)
    try:
        data = await read_public_aircraft(batch_id)
        if data is None:
            return JSONResponse({"status": "expired_or_unavailable", "detail": "This exact publication is unavailable; no newer batch is substituted"}, status_code=410)
        headers = {"Content-Disposition": 'attachment; filename="adsb-lol-odbl-snapshot.json"'} if batch_id else {}
        return JSONResponse(data, headers=headers)
    except Exception:
        return JSONResponse({"status": "unavailable", "detail": "Publication unavailable; coverage is unknown"}, status_code=503)


@app.post("/satellite/poll", dependencies=[Depends(require_admin_key)])
async def satellite_poll_now():
    if not settings.live_ingestion_enabled or not settings.firms_map_key:
        raise HTTPException(status_code=503, detail="Thermal observation collection is not configured")
    current = runtime.tasks.get("manual_firms")
    if current and not current.done():
        raise HTTPException(status_code=409, detail="A poll is already running")
    from app.services.satellite_firms import poll_firms_once
    runtime.start("manual_firms", poll_firms_once())
    return {"status": "poll triggered"}
