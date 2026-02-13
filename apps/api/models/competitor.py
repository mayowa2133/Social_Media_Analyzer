"""Competitor model for competitor channels."""

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class Competitor(Base):
    """Competitor channel being tracked."""
    
    __tablename__ = "competitors"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)
    handle = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    subscriber_count = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="competitors")
