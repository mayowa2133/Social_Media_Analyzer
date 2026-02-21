"""Feed workflow telemetry event model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.sql import func

from database import Base


class FeedTelemetryEvent(Base):
    """Structured telemetry event for feed workflow instrumentation."""

    __tablename__ = "feed_telemetry_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    event_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="ok", index=True)
    platform = Column(String, nullable=True, index=True)
    source_item_id = Column(String, ForeignKey("research_items.id"), nullable=True, index=True)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
