"""Downloaded media asset model."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class MediaAsset(Base):
    """Downloaded media file persisted for audit processing."""

    __tablename__ = "media_assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    transcript_status = Column(String, nullable=False, default="pending")
    upload_id = Column(String, ForeignKey("uploads.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="media_assets")
    upload = relationship("Upload", back_populates="media_asset")
    jobs = relationship("MediaDownloadJob", back_populates="media_asset")
