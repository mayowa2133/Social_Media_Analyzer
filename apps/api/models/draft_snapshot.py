"""DraftSnapshot model for edited script iterations."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class DraftSnapshot(Base):
    """Persisted edited script draft with rescore outputs."""

    __tablename__ = "draft_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    source_item_id = Column(String, ForeignKey("research_items.id"), nullable=True, index=True)
    variant_id = Column(String, nullable=True, index=True)
    script_text = Column(Text, nullable=False)
    baseline_score = Column(Float, nullable=True)
    rescored_score = Column(Float, nullable=False)
    delta_score = Column(Float, nullable=True)
    detector_rankings_json = Column(JSON, nullable=True)
    next_actions_json = Column(JSON, nullable=True)
    line_level_edits_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="draft_snapshots")
