"""Audit model for performance audits."""

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class Audit(Base):
    """Performance audit for a user's channel."""
    
    __tablename__ = "audits"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    progress = Column(String, default="0")
    input_json = Column(JSON, nullable=True)  # Config for this audit
    output_json = Column(JSON, nullable=True)  # Results
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="audits")
