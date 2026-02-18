"""ReportShareLink model for shareable report URLs."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class ReportShareLink(Base):
    """Public share link token for a specific audit report."""

    __tablename__ = "report_share_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False, index=True)
    share_token = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="report_share_links")
    audit = relationship("Audit", back_populates="share_links")
