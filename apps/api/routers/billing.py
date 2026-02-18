"""Billing and credits router."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import get_db
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.credits import add_credit_purchase, get_credit_summary

router = APIRouter()
logger = logging.getLogger(__name__)


class CheckoutRequest(BaseModel):
    user_id: Optional[str] = None
    credits: int = Field(default=25, ge=1, le=10000)


class CreditTopUpRequest(BaseModel):
    user_id: Optional[str] = None
    credits: int = Field(ge=1, le=10000)
    billing_reference: Optional[str] = None


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(id=user_id, email=f"{user_id}@local.invalid")
    db.add(user)
    await db.flush()
    return user


@router.get("/credits")
async def credits_summary(
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_credit_summary(scoped_user_id, db)


@router.post("/checkout")
async def create_checkout_session(
    request: CheckoutRequest,
    _rate_limit: None = Depends(rate_limit("billing_checkout", limit=20, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)

    if not settings.BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Billing is disabled. Enable BILLING_ENABLED to use checkout.")

    # Stripe integration is intentionally minimal; return deterministic payload until webhook wiring is enabled.
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="Stripe is not configured.")

    return {
        "checkout_url": settings.STRIPE_SUCCESS_URL,
        "user_id": scoped_user_id,
        "credits": request.credits,
        "status": "stub",
        "detail": "Checkout stub configured. Replace with Stripe Checkout Session creation.",
    }


@router.post("/topup")
async def manual_topup(
    request: CreditTopUpRequest,
    _rate_limit: None = Depends(rate_limit("billing_topup", limit=30, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)

    if settings.BILLING_ENABLED and not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing enabled but Stripe is not configured.")

    billing_reference = request.billing_reference or f"manual:{request.credits}"
    result = await add_credit_purchase(
        user_id=scoped_user_id,
        db=db,
        credits=request.credits,
        provider="manual",
        billing_reference=billing_reference,
    )
    return {
        "ok": True,
        "credits_added": request.credits,
        "balance_after": result.get("balance_after", 0),
    }
