"""Feed source follow model for scheduled auto-ingest."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class FeedSourceFollow(Base):
    """Saved feed source query that can be ingested on a schedule."""

    __tablename__ = "feed_source_follows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False, index=True)
    query = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False, default="7d")
    sort_by = Column(String, nullable=False, default="trending_score")
    sort_direction = Column(String, nullable=False, default="desc")
    limit = Column(Integer, nullable=False, default=20)
    cadence_minutes = Column(Integer, nullable=False, default=360)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
