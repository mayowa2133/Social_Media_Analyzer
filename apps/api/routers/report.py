"""
Router for generating and retrieving audit reports.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_db
from services.report import get_consolidated_report

router = APIRouter()

@router.get("/latest")
async def get_latest_report(
    user_id: str = "test-user",
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the latest consolidated report for the user."""
    try:
        return await get_consolidated_report(user_id, None, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{audit_id}")
async def get_report_by_id(
    audit_id: str,
    user_id: str = "test-user",
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a specific consolidated report."""
    try:
        return await get_consolidated_report(user_id, audit_id, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
