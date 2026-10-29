"""Conflict Monitor API. Startup never implicitly enables live collection."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.config import settings
from app.db import engine, async_session
from app.security import require_admin_key
from app.services.runtime import runtime
from app.routes.channels import router as channels_router
from app.routes.events import router as events_router
from app.routes.tracking import router as tracking_router
from app.routes.ws import router as ws_router
from app.routes.market import router as market_router
from app.routes.sitreps import router as sitreps_router
from app.routes.media import router as media_router
from app.routes.costs import router as costs_router
from app.routes.briefing import router as briefing_router

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
        if settings.demo_mode:
            from app.services.demo import seed_demo_history, start_demo_event_generator, start_demo_aircraft_poller, start_demo_vessel_poller
            await seed_demo_history(300)
            runtime.start("demo_events", start_demo_event_generator())
            runtime.start("demo_aircraft", start_demo_aircraft_poller())
            runtime.start("demo_vessels", start_demo_vessel_poller())
        elif settings.live_ingestion_enabled:
            from app.services.telegram import start_telegram_listener
            from app.services.opensky import start_opensky_poller
            from app.services.maritime import start_maritime_poller
            from app.services.satellites import start_tle_fetcher
            from app.services.news_feeds import start_news_feed_poller, start_x_poller
            from app.services.snapshots import start_snapshot_recorder
            from app.services.retro_matcher import start_retro_matcher
            from app.services.satellite_firms import start_firms_poller
            if settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session and settings.telegram_channels:
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
            if settings.enable_sitrep_generation and settings.anthropic_api_key:
                from app.services.sitrep_generator import start_sitrep_generator
                runtime.start("sitreps", start_sitrep_generator())
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



app = FastAPI(title="Conflict Monitor", version="0.2.0-rc.1", lifespan=lifespan)
origins = [s.strip() for s in settings.cors_origins.split(",") if s.strip()] or [
    "http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-Admin-Key"])
for router in (channels_router, events_router, tracking_router, ws_router,
               market_router, sitreps_router, media_router, costs_router, briefing_router):
    app.include_router(router)


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
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
            for table in ("events", "source_reports", "sitreps", "intel_media", "usage_log", "cost_config", "tracking_snapshots", "channel_checkpoints"):
                await session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        optional_failures = {name: error for name, error in runtime.failures.items() if name in OPTIONAL_JOB_NAMES}
        failed = any(name not in OPTIONAL_JOB_NAMES for name in runtime.failures)
        return JSONResponse({"status": "degraded" if failed else "healthy",
            "database": "connected", "live_ingestion_enabled": settings.live_ingestion_enabled,
            "optional_job_failures": optional_failures,
            "provider_health": "see /status; task liveness does not establish data freshness"},
            status_code=503 if failed else 200)
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "unavailable_or_schema_missing"}, status_code=503)


@app.get("/status")
async def status():
    from app.services.satellites import get_tle_status
    from app.services.opensky import get_aircraft_status
    from app.services.maritime import get_maritime_status
    from app.services.news_feeds import get_feed_status
    from app.services.satellite_firms import get_firms_status
    from app.services.telegram import get_telegram_status
    return {**runtime.snapshot(), "mode": "synthetic" if settings.demo_mode else
        "live" if settings.live_ingestion_enabled else "collection_disabled",
        "satellites": get_tle_status(),
        "aircraft": get_aircraft_status(),
        "maritime": get_maritime_status(),
        "news_feeds": get_feed_status(),
        "thermal_observations": get_firms_status(),
        "telegram": get_telegram_status(),
        "limitations": ["Provider freshness does not establish report truth or completeness.",
                        "Source diversity is not independent corroboration."]}


@app.get("/config")
async def config():
    return {"demo_mode": settings.demo_mode,
        "live_ingestion_enabled": settings.live_ingestion_enabled,
        "generation_enabled": settings.enable_sitrep_generation,
        "video_generation_enabled": settings.enable_video_generation,
        "local_ai_enabled": settings.enable_local_ai,
        "rss_processing_mode": settings.rss_processing_mode,
        "google_earth_enabled": settings.google_earth_enabled and bool(settings.google_maps_browser_key),
        "google_maps_browser_key": settings.google_maps_browser_key if settings.google_earth_enabled else "",
        "sentinel_hub_instance_id": settings.sentinel_hub_instance_id,
        "version": app.version, "conflict_start_date": settings.conflict_start_date}


@app.get("/satellite/hotspots")
async def satellite_hotspots():
    from app.services.satellite_firms import get_last_hotspots
    return get_last_hotspots()


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
