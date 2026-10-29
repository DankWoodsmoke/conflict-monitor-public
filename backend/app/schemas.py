from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class EventCreate(BaseModel):
    source: str = "telegram"
    channel_name: str = ""
    raw_text: str = ""
    summary: str = ""
    event_type: str = "military"
    severity: int = 5
    lat: float | None = None
    lon: float | None = None
    timestamp: datetime | None = None


class EventRead(BaseModel):
    id: int
    source: str
    channel_name: str
    raw_text: str
    summary: str
    event_type: str
    severity: int
    lat: float | None
    lon: float | None
    timestamp: datetime
    created_at: datetime
    report_count: int = 1
    reporting_channels: str = ""
    source_reliability: int | None = None
    location_name: str = ""
    telegram_message_id: int | None = None
    source_url: str = ""
    anomaly_score: int = 0
    anomaly_analysis: str = ""
    confirmed_networks: str = ""
    classification_status: str = "legacy_unknown"
    geolocation_precision: str = "unknown"
    reports: list[dict] = Field(default_factory=list)

    @computed_field
    @property
    def evidence(self) -> dict:
        from app.services.evidence import assess_evidence
        return assess_evidence(self)

    model_config = {"from_attributes": True}


class EventWS(BaseModel):
    """Payload pushed over WebSocket."""
    type: str = "new_event"
    event: EventRead
