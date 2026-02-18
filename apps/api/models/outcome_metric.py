"""OutcomeMetric model for post-publication actual performance."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class OutcomeMetric(Base):
    """Actual outcome snapshot used for calibration and confidence."""

    __tablename__ = "outcome_metrics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    content_item_id = Column(String, ForeignKey("research_items.id"), nullable=True, index=True)
    draft_snapshot_id = Column(String, ForeignKey("draft_snapshots.id"), nullable=True, index=True)
    report_id = Column(String, ForeignKey("audits.id"), nullable=True, index=True)
    platform = Column(String, nullable=False, index=True)
    video_external_id = Column(String, nullable=False, index=True)
    posted_at = Column(DateTime(timezone=True), nullable=False)
    actual_metrics_json = Column(JSON, nullable=False)
    retention_points_json = Column(JSON, nullable=True)
    predicted_score = Column(Float, nullable=True)
    actual_score = Column(Float, nullable=True)
    calibration_delta = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="outcome_metrics")
