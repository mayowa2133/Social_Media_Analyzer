"""Video model for social media videos."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class Video(Base):
    """Video from a profile or competitor."""
    
    __tablename__ = "videos"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=True)
    competitor_id = Column(String, ForeignKey("competitors.id"), nullable=True)
    platform = Column(String, nullable=False)
    external_id = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    duration_s = Column(Integer, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    profile = relationship("Profile", back_populates="videos")
    metrics = relationship("VideoMetrics", back_populates="video", cascade="all, delete-orphan")
