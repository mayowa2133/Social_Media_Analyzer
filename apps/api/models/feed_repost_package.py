"""Feed repost package model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.sql import func

from database import Base


class FeedRepostPackage(Base):
    """Saved repost package generated from a feed/research item."""

    __tablename__ = "feed_repost_packages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    source_item_id = Column(String, ForeignKey("research_items.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    target_platforms_json = Column(JSON, nullable=True)
    package_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
