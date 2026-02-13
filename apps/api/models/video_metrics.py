"""VideoMetrics model for video statistics."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class VideoMetrics(Base):
    """Metrics for a specific video at a point in time."""
    
    __tablename__ = "video_metrics"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    watch_time_hours = Column(Float, nullable=True)  # YouTube Analytics
    avg_view_duration_s = Column(Float, nullable=True)  # YouTube Analytics
    ctr = Column(Float, nullable=True)  # Click-through rate (YouTube Analytics)
    retention_points_json = Column(JSON, nullable=True)  # Retention curve data
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    video = relationship("Video", back_populates="metrics")
