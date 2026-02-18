"""CreditLedger model for freemium usage accounting."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class CreditLedger(Base):
    """Immutable credit ledger entry."""

    __tablename__ = "credit_ledger"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    entry_type = Column(String, nullable=False)
    delta_credits = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)
    reference_type = Column(String, nullable=True)
    reference_id = Column(String, nullable=True)
    billing_provider = Column(String, nullable=True)
    billing_reference = Column(String, nullable=True)
    period_key = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="credit_entries")
