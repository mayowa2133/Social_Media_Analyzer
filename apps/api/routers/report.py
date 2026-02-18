"""
Router for generating and retrieving audit reports.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from services.report import get_consolidated_report
from services.report_share import create_report_share_link, resolve_shared_report

router = APIRouter()
logger = logging.getLogger(__name__)


class ShareReportRequest(BaseModel):
    user_id: str | None = None
    expires_hours: int = Field(default=168, ge=1, le=720)

@router.get("/latest")
async def get_latest_report(
    user_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the latest consolidated report for the user."""
    try:
        scoped_user_id = ensure_user_scope(auth.user_id, user_id)
        return await get_consolidated_report(scoped_user_id, None, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="No report found for this user.")
    except Exception as e:
        logger.exception("Failed to get latest report for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch latest report.")


@router.get("/shared/{share_token}")
async def get_shared_report(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public report retrieval via signed share token."""
    try:
        return await resolve_shared_report(share_token=share_token, db=db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to resolve shared report token=%s", share_token)
        raise HTTPException(status_code=500, detail="Failed to fetch shared report.")


@router.post("/{audit_id}/share")
async def create_share_link(
    audit_id: str,
    request: ShareReportRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a shareable link for a report."""
    try:
        scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
        payload = await create_report_share_link(
            user_id=scoped_user_id,
            audit_id=audit_id,
            db=db,
            expires_hours=request.expires_hours,
        )
        app_origin = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
        payload["share_url"] = f"{app_origin.rstrip('/')}/report/shared/{payload['share_token']}"
        return payload
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create share link for audit=%s", audit_id)
        raise HTTPException(status_code=500, detail="Failed to create share link.")

@router.get("/{audit_id}")
async def get_report_by_id(
    audit_id: str,
    user_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a specific consolidated report."""
    try:
        scoped_user_id = ensure_user_scope(auth.user_id, user_id)
        return await get_consolidated_report(scoped_user_id, audit_id, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="Report not found.")
    except Exception as e:
        logger.exception("Failed to get report audit_id=%s user_id=%s", audit_id, user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch report.")
