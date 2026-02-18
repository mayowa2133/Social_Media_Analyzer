"""ResearchItem model for normalized cross-platform research content."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class ResearchItem(Base):
    """Normalized content item used in research/discovery/optimizer flows."""

    __tablename__ = "research_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    collection_id = Column(String, ForeignKey("research_collections.id"), nullable=True, index=True)
    platform = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, default="manual_url")
    url = Column(String, nullable=True)
    external_id = Column(String, nullable=True, index=True)
    creator_handle = Column(String, nullable=True, index=True)
    creator_display_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    media_meta_json = Column(JSON, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="research_items")
    collection = relationship("ResearchCollection", back_populates="items")
