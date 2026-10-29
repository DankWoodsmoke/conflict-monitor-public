from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/conflict_monitor"
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    anthropic_api_key: str = ""
    telegram_session: str = ""   # StringSession token written by auth.py (preferred over file session)
    telegram_channels: str = ""  # explicit comma-separated public channel usernames
    telegram_processing_mode: Literal["reports", "model"] = "reports"
    telegram_startup_max_messages: int = Field(20, ge=1, le=100)
    opensky_username: str = ""
    opensky_password: str = ""
    aisstream_api_key: str = ""
    demo_mode: bool = False
    # Collection and paid model work require explicit operator opt-in.
    live_ingestion_enabled: bool = False
    x_ingestion_enabled: bool = False
    enable_sitrep_generation: bool = False
    enable_video_generation: bool = False
    # Optional self-hosted AI; no cloud URLs, downloads or shared runtime startup.
    enable_local_ai: bool = False
    local_ai_url: str = "http://127.0.0.1:11501"
    local_ai_model: str = "qwen3.5:4b"
    local_ai_timeout_seconds: float = Field(180, ge=5, le=600)
    local_ai_num_gpu: int = Field(0, ge=0, le=99)
    briefing_artifact_dir: str = "./videos/briefing"
    briefing_max_age_hours: int = Field(24, ge=1, le=48)
    piper_model_path: str = ""
    piper_python: str = ""  # defaults to this Python interpreter; CPU only
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    classification_model: str = "claude-haiku-4-5-20251001"
    sitrep_model: str = "claude-sonnet-4-6"
    model_timeout_seconds: float = 30.0
    # Free mode preserves publisher metadata without paid extraction or guessed scores.
    rss_processing_mode: Literal["reports", "model"] = "reports"
    rss_relevance_mode: Literal["keywords", "selected_sources"] = "keywords"
    rss_sources: str = ""  # optional comma-separated IDs from the fixed registry
    rss_max_items_per_feed: int = Field(20, ge=1, le=100)
    rss_max_ingest_per_cycle: int = Field(60, ge=1, le=500)
    rss_max_response_bytes: int = Field(2_000_000, ge=1024, le=5_000_000)
    rss_poll_interval_seconds: int = Field(300, ge=60, le=3600)
    # Geocoding defaults to a local gazetteer; configure a compliant service explicitly.
    nominatim_url: str = ""
    nominatim_user_agent: str = "ConflictMonitor/0.2 (self-hosted)"
    # Comma-separated allowed CORS origins (e.g. "http://localhost:5173,https://myapp.com")
    cors_origins: str = ""
    # Admin API key — required for all /admin/ endpoints (set in .env)
    admin_api_key: str = ""
    # Public browser key, deliberately exposed only when operator-enabled.
    # Use a Maps/HTTP-referrer-restricted key, never a server credential.
    google_earth_enabled: bool = False
    google_maps_browser_key: str = ""
    # Only ingest events on or after this date (ISO YYYY-MM-DD)
    conflict_start_date: str = "2026-02-28"
    # NASA FIRMS MAP_KEY — free at https://firms.modaps.eosdis.nasa.gov/api/map_key/
    # Enables noncausal satellite thermal-observation context
    firms_map_key: str = ""
    # Sentinel Hub instance ID — free account at https://dataspace.copernicus.eu/
    # Enables optional imagery links; event occurrence and capture date remain separate
    sentinel_hub_instance_id: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
