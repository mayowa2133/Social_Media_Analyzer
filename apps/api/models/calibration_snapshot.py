"""CalibrationSnapshot model for model confidence tracking."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class CalibrationSnapshot(Base):
    """Aggregate calibration stats for a user/platform combination."""

    __tablename__ = "calibration_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    sample_size = Column(Integer, nullable=False, default=0)
    mean_abs_error = Column(Float, nullable=False, default=0.0)
    hit_rate = Column(Float, nullable=False, default=0.0)
    trend = Column(String, nullable=False, default="flat")
    recommendations_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="calibration_snapshots")
