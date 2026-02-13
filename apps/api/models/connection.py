"""Connection model for OAuth tokens."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class Connection(Base):
    """OAuth connection for platforms like YouTube."""
    
    __tablename__ = "connections"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)  # youtube, tiktok, instagram
    platform_user_id = Column(String, nullable=True, index=True)
    platform_handle = Column(String, nullable=True)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="connections")
