"""Blueprint snapshot cache model."""

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class BlueprintSnapshot(Base):
    """Cached blueprint payload per user."""

    __tablename__ = "blueprint_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    payload_json = Column(JSON, nullable=False)
    competitor_signature = Column(String, nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="blueprint_snapshot")
