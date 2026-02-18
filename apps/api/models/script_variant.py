"""ScriptVariant model for generated script options."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class ScriptVariant(Base):
    """Persisted script generation batch and ranked variants."""

    __tablename__ = "script_variants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    source_item_id = Column(String, ForeignKey("research_items.id"), nullable=True, index=True)
    platform = Column(String, nullable=False, index=True)
    topic = Column(String, nullable=False)
    request_json = Column(JSON, nullable=True)
    variants_json = Column(JSON, nullable=False)
    selected_variant_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="script_variants")
