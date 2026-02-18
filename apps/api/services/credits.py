"""Credit ledger and usage accounting helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from models.credit_ledger import CreditLedger


def _current_period_key(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y-%m")


async def get_credit_balance(user_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(CreditLedger.delta_credits), 0)).where(CreditLedger.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def _insert_entry(
    user_id: str,
    db: AsyncSession,
    *,
    entry_type: str,
    delta_credits: int,
    reason: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    billing_provider: Optional[str] = None,
    billing_reference: Optional[str] = None,
    period_key: Optional[str] = None,
) -> CreditLedger:
    current_balance = await get_credit_balance(user_id, db)
    next_balance = current_balance + int(delta_credits)
    entry = CreditLedger(
        id=str(uuid.uuid4()),
        user_id=user_id,
        entry_type=entry_type,
        delta_credits=int(delta_credits),
        balance_after=next_balance,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        billing_provider=billing_provider,
        billing_reference=billing_reference,
        period_key=period_key,
    )
    db.add(entry)
    await db.flush()
    return entry


async def ensure_monthly_credit_grant(user_id: str, db: AsyncSession) -> int:
    period_key = _current_period_key()
    existing = await db.execute(
        select(CreditLedger.id).where(
            CreditLedger.user_id == user_id,
            CreditLedger.entry_type == "monthly_grant",
            CreditLedger.period_key == period_key,
        )
    )
    if existing.scalar_one_or_none():
        return await get_credit_balance(user_id, db)

    await _insert_entry(
        user_id=user_id,
        db=db,
        entry_type="monthly_grant",
        delta_credits=max(int(settings.FREE_MONTHLY_CREDITS), 0),
        reason="Monthly free credits grant",
        period_key=period_key,
    )
    await db.commit()
    return await get_credit_balance(user_id, db)


async def consume_credits(
    user_id: str,
    db: AsyncSession,
    *,
    cost: int,
    reason: str,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> Dict[str, Any]:
    debit_cost = max(int(cost), 0)
    if debit_cost == 0:
        balance = await get_credit_balance(user_id, db)
        return {"charged": 0, "balance_after": balance}

    await ensure_monthly_credit_grant(user_id, db)
    balance = await get_credit_balance(user_id, db)
    if balance < debit_cost:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Insufficient credits. Required: {debit_cost}, available: {balance}. "
                "Top up credits to continue."
            ),
        )

    await _insert_entry(
        user_id=user_id,
        db=db,
        entry_type="debit",
        delta_credits=-debit_cost,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    await db.commit()
    balance_after = await get_credit_balance(user_id, db)
    return {"charged": debit_cost, "balance_after": balance_after}


async def add_credit_purchase(
    user_id: str,
    db: AsyncSession,
    *,
    credits: int,
    provider: str,
    billing_reference: str,
    reason: str = "Credit purchase",
) -> Dict[str, Any]:
    grant = max(int(credits), 0)
    if grant <= 0:
        raise HTTPException(status_code=422, detail="credits must be greater than 0")
    await _insert_entry(
        user_id=user_id,
        db=db,
        entry_type="purchase",
        delta_credits=grant,
        reason=reason,
        billing_provider=provider,
        billing_reference=billing_reference,
    )
    await db.commit()
    return {"balance_after": await get_credit_balance(user_id, db)}


async def get_credit_summary(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    balance = await ensure_monthly_credit_grant(user_id, db)
    period_key = _current_period_key()
    result = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(30)
    )
    entries = result.scalars().all()
    return {
        "balance": balance,
        "period_key": period_key,
        "free_monthly_credits": max(int(settings.FREE_MONTHLY_CREDITS), 0),
        "costs": {
            "research_search": max(int(settings.CREDIT_COST_RESEARCH_SEARCH), 0),
            "optimizer_variants": max(int(settings.CREDIT_COST_OPTIMIZER_VARIANTS), 0),
            "audit_run": max(int(settings.CREDIT_COST_AUDIT_RUN), 0),
        },
        "recent_entries": [
            {
                "id": entry.id,
                "entry_type": entry.entry_type,
                "delta_credits": entry.delta_credits,
                "balance_after": entry.balance_after,
                "reason": entry.reason,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in entries
        ],
    }
