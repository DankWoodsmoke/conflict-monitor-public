import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source", "channel_name", "telegram_message_id", name="uq_event_source_channel_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="telegram")
    channel_name: Mapped[str] = mapped_column(String(255), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    event_type: Mapped[str] = mapped_column(String(50), default="military")
    severity: Mapped[int] = mapped_column(Integer, default=5)
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
    classification_status: Mapped[str] = mapped_column(String(30), default="legacy_unknown")
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
