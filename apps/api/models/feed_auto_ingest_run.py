"""Feed auto-ingest run model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class FeedAutoIngestRun(Base):
    """Execution record for manual/scheduled follow ingest."""

    __tablename__ = "feed_auto_ingest_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    follow_id = Column(String, ForeignKey("feed_source_follows.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    item_count = Column(Integer, nullable=False, default=0)
    item_ids_json = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
