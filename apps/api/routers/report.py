"""
Router for generating and retrieving audit reports.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.report import get_consolidated_report

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/latest")
async def get_latest_report(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the latest consolidated report for the user."""
    try:
        return await get_consolidated_report(user_id, None, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="No report found for this user.")
    except Exception as e:
        logger.exception("Failed to get latest report for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch latest report.")

@router.get("/{audit_id}")
async def get_report_by_id(
    audit_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a specific consolidated report."""
    try:
        return await get_consolidated_report(user_id, audit_id, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="Report not found.")
    except Exception as e:
        logger.exception("Failed to get report audit_id=%s user_id=%s", audit_id, user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch report.")
