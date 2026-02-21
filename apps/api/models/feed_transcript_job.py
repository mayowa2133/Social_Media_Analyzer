"""Feed transcript job model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class FeedTranscriptJob(Base):
    """Queued transcript extraction job for a research/feed item."""

    __tablename__ = "feed_transcript_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    research_item_id = Column(String, ForeignKey("research_items.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)
    queue_job_id = Column(String, nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    transcript_source = Column(String, nullable=True)
    transcript_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
