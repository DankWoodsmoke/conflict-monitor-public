import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PublicObservationBatch(Base):
    """Dedicated publication receipts; never contains private event references."""
    __tablename__ = "public_observation_batches"
    __table_args__ = (Index("ix_public_observation_source_time", "source", "published_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PublicAircraftBatch(Base):
    """Independent ODbL derivative snapshots; never combined with report data."""
    __tablename__ = "public_aircraft_batches"
    __table_args__ = (Index("ix_public_aircraft_source_time", "source", "published_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source", "channel_name", "telegram_message_id", name="uq_event_source_channel_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="telegram")
    channel_name: Mapped[str] = mapped_column(String(255), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    event_type: Mapped[str] = mapped_column(String(50), default="unclassified")
    severity: Mapped[int] = mapped_column(Integer, default=0)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    reporting_channels: Mapped[str] = mapped_column(Text, default="")
    source_reliability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str] = mapped_column(Text, default="")
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    anomaly_score: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_analysis: Mapped[str] = mapped_column(Text, default="")
    confirmed_networks: Mapped[str] = mapped_column(Text, default="")
    classification_status: Mapped[str] = mapped_column(String(30), default="not_requested")
    geolocation_precision: Mapped[str] = mapped_column(String(30), default="unknown")
    reports: Mapped[list] = mapped_column(JSONB, default=list)


class TrackingSnapshot(Base):
    """Periodic snapshot of aircraft, vessel, and jamming zone positions.
    Used for historical replay. One row every 2 minutes."""
    __tablename__ = "tracking_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), index=True, unique=True
    )
    aircraft: Mapped[dict] = mapped_column(JSONB, default=list)
    vessels: Mapped[dict] = mapped_column(JSONB, default=list)
    jamming_zones: Mapped[dict] = mapped_column(JSONB, default=list)


class ChannelCheckpoint(Base):
    """Stores the highest processed Telegram message_id per channel.
    On restart, backfill only fetches messages NEWER than this ID,
    so we never re-process old data or waste API credits.
    """
    __tablename__ = "channel_checkpoints"

    channel_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_message_id: Mapped[int] = mapped_column(Integer, default=0)
    last_processed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

class Sitrep(Base):
    """AI-generated strategic situation report, created every 4h or on event threshold."""
    __tablename__ = "sitreps"

    id:                  Mapped[int]             = mapped_column(Integer, primary_key=True)
    generated_at:        Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    trigger:             Mapped[str]             = mapped_column(String(20), default="time")   # "time"|"event_count"|"critical"
    events_analyzed:     Mapped[int]             = mapped_column(Integer, default=0)
    headline:            Mapped[str]             = mapped_column(Text, default="")
    situation:           Mapped[str]             = mapped_column(Text, default="")
    escalation_text:     Mapped[str]             = mapped_column(Text, default="")
    escalation_level:    Mapped[str]             = mapped_column(String(20), default="STABLE")  # STABLE|ELEVATED|ESCALATING|CRITICAL|WARTIME
    escalation_score:    Mapped[int]             = mapped_column(Integer, default=50)            # 0-100 computed Escalation Index
    economic_exposure:   Mapped[str]             = mapped_column(Text, default="")
    game_theory:         Mapped[str]             = mapped_column(Text, default="")
    historical_analogue: Mapped[str]             = mapped_column(Text, default="")
    humanitarian_ground: Mapped[str]             = mapped_column(Text, default="")
    key_questions:       Mapped[str]             = mapped_column(Text, default="")   # JSON array of {q, a, watch}
    key_event_ids:       Mapped[str]             = mapped_column(Text, default="")   # comma-separated
    raw_response:        Mapped[str]             = mapped_column(Text, default="")   # full JSON



class IntelMedia(Base):
    """Chart/image captured from an analytical X account tweet."""
    __tablename__ = "intel_media"

    id:           Mapped[int]              = mapped_column(Integer, primary_key=True)
    captured_at:  Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    tweet_id:     Mapped[str]              = mapped_column(String(30), unique=True, index=True)
    source:       Mapped[str]              = mapped_column(String(60), default="")   # e.g. x_lynalden
    username:     Mapped[str]              = mapped_column(String(60), default="")
    image_url:    Mapped[str]              = mapped_column(Text, default="")
    thumb_url:    Mapped[str]              = mapped_column(Text, default="")
    media_type:   Mapped[str]              = mapped_column(String(20), default="photo")
    tweet_text:   Mapped[str]              = mapped_column(Text, default="")
    tweet_url:    Mapped[str]              = mapped_column(Text, default="")


class UsageLog(Base):
    __tablename__ = "usage_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    operation: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class CostConfig(Base):
    __tablename__ = "cost_config"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class SourceReport(Base):
    """Immutable incoming content; status records processing, not factual truth."""
    __tablename__ = "source_reports"
    identity: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TelegramBackfillJob(Base):
    """Explicit bounded history scan; never a live-collection checkpoint."""
    __tablename__ = "telegram_backfill_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_messages: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    source_entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    upper_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cursor_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    processed_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcomes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    blocked_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramBackfillItem(Base):
    """Hashes and outcomes link the history cursor to preserved source receipts."""
    __tablename__ = "telegram_backfill_items"
    job_id: Mapped[str] = mapped_column(ForeignKey("telegram_backfill_jobs.id"), primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_report_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timestamp: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    recorded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceReportRetry(Base):
    """Operational retry state; the source receipt remains immutable."""
    __tablename__ = "source_report_retries"
    __table_args__ = (Index("ix_source_retry_pending_due", "source_name", "next_attempt_at", "identity",
                           postgresql_where=text("finished_at IS NULL")),)
    identity: Mapped[str] = mapped_column(ForeignKey("source_reports.identity"), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_attempt_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
