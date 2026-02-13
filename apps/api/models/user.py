"""User model."""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class User(Base):
    """User model for authenticated users."""
    
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    connections = relationship("Connection", back_populates="user", cascade="all, delete-orphan")
    profiles = relationship("Profile", back_populates="user", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="user", cascade="all, delete-orphan")
    audits = relationship("Audit", back_populates="user", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="user", cascade="all, delete-orphan")
