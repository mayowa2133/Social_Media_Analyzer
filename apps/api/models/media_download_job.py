"""Media download job model."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class MediaDownloadJob(Base):
    """Queued media download/transcode job."""

    __tablename__ = "media_download_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)
    queue_job_id = Column(String, nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    media_asset_id = Column(String, ForeignKey("media_assets.id"), nullable=True, index=True)
    upload_id = Column(String, ForeignKey("uploads.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="media_download_jobs")
    media_asset = relationship("MediaAsset", back_populates="jobs")
