"""UX-focused endpoints for guided workflow state."""

from typing import Dict, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models.audit import Audit
from models.competitor import Competitor
from models.connection import Connection
from models.draft_snapshot import DraftSnapshot
from models.outcome_metric import OutcomeMetric
from models.research_item import ResearchItem
from models.script_variant import ScriptVariant
from routers.auth_scope import AuthContext, get_auth_context

router = APIRouter()


FlowAction = Literal[
    "connect_platform",
    "add_competitors",
    "import_research",
    "generate_script",
    "run_audit",
    "post_outcome",
    "optimize_loop",
]


class FlowStateResponse(BaseModel):
    connected_platforms: Dict[str, bool] = Field(default_factory=dict)
    has_competitors_by_platform: Dict[str, bool] = Field(default_factory=dict)
    has_research_items_by_platform: Dict[str, bool] = Field(default_factory=dict)
    has_script_variants: bool = False
    has_completed_audit: bool = False
    has_report: bool = False
    has_outcomes: bool = False
    next_best_action: FlowAction
    next_best_href: str
    completion_percent: int
    stage_completion: Dict[str, bool] = Field(default_factory=dict)
    totals: Dict[str, int] = Field(default_factory=dict)
    preferred_platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None


def _pick_next_action(
    *,
    connected_any: bool,
    competitor_any: bool,
    research_any: bool,
    script_any: bool,
    audit_any: bool,
    outcomes_any: bool,
) -> tuple[FlowAction, str]:
    if not connected_any:
        return "connect_platform", "/connect"
    if not competitor_any:
        return "add_competitors", "/competitors"
    if not research_any:
        return "import_research", "/research"
    if not script_any:
        return "generate_script", "/research?mode=optimizer"
    if not audit_any:
        return "run_audit", "/audit/new"
    if not outcomes_any:
        return "post_outcome", "/report/latest"
    return "optimize_loop", "/research?mode=optimizer"


@router.get("/flow_state", response_model=FlowStateResponse)
async def get_flow_state(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    platforms = ("youtube", "instagram", "tiktok")

    connected_platforms = {platform: False for platform in platforms}
    connected_rows = await db.execute(
        select(Connection.platform)
        .where(
            Connection.user_id == auth.user_id,
            Connection.platform.in_(platforms),
        )
        .distinct()
    )
    for platform in connected_rows.scalars().all():
        normalized = str(platform or "").lower()
        if normalized in connected_platforms:
            connected_platforms[normalized] = True

    competitor_counts = {platform: 0 for platform in platforms}
    competitor_rows = await db.execute(
        select(Competitor.platform, func.count(Competitor.id))
        .where(
            Competitor.user_id == auth.user_id,
            Competitor.platform.in_(platforms),
        )
        .group_by(Competitor.platform)
    )
    for platform, count in competitor_rows.all():
        normalized = str(platform or "").lower()
        if normalized in competitor_counts:
            competitor_counts[normalized] = int(count or 0)

    research_counts = {platform: 0 for platform in platforms}
    research_rows = await db.execute(
        select(ResearchItem.platform, func.count(ResearchItem.id))
        .where(
            ResearchItem.user_id == auth.user_id,
            ResearchItem.platform.in_(platforms),
        )
        .group_by(ResearchItem.platform)
    )
    for platform, count in research_rows.all():
        normalized = str(platform or "").lower()
        if normalized in research_counts:
            research_counts[normalized] = int(count or 0)

    script_variant_count_result = await db.execute(
        select(func.count(ScriptVariant.id)).where(ScriptVariant.user_id == auth.user_id)
    )
    script_variant_count = int(script_variant_count_result.scalar() or 0)

    draft_snapshot_count_result = await db.execute(
        select(func.count(DraftSnapshot.id)).where(DraftSnapshot.user_id == auth.user_id)
    )
    draft_snapshot_count = int(draft_snapshot_count_result.scalar() or 0)

    completed_audit_count_result = await db.execute(
        select(func.count(Audit.id)).where(
            Audit.user_id == auth.user_id,
            Audit.status == "completed",
        )
    )
    completed_audit_count = int(completed_audit_count_result.scalar() or 0)

    outcome_count_result = await db.execute(
        select(func.count(OutcomeMetric.id)).where(OutcomeMetric.user_id == auth.user_id)
    )
    outcome_count = int(outcome_count_result.scalar() or 0)

    connected_any = any(connected_platforms.values())
    competitor_any = sum(competitor_counts.values()) > 0
    research_any = sum(research_counts.values()) > 0
    script_any = (script_variant_count + draft_snapshot_count) > 0
    audit_any = completed_audit_count > 0
    outcomes_any = outcome_count > 0

    next_best_action, next_best_href = _pick_next_action(
        connected_any=connected_any,
        competitor_any=competitor_any,
        research_any=research_any,
        script_any=script_any,
        audit_any=audit_any,
        outcomes_any=outcomes_any,
    )

    stage_completion = {
        "connected_platform": connected_any,
        "competitors_added": competitor_any,
        "research_collected": research_any,
        "script_generated": script_any,
        "audit_completed": audit_any,
        "outcome_recorded": outcomes_any,
    }
    completed_steps = sum(1 for value in stage_completion.values() if value)
    completion_percent = int(round((completed_steps / len(stage_completion)) * 100))

    preferred_platform = None
    for platform in platforms:
        if connected_platforms[platform]:
            preferred_platform = platform
            break
    if preferred_platform is None:
        for platform in platforms:
            if research_counts[platform] > 0:
                preferred_platform = platform
                break

    return FlowStateResponse(
        connected_platforms=connected_platforms,
        has_competitors_by_platform={key: value > 0 for key, value in competitor_counts.items()},
        has_research_items_by_platform={key: value > 0 for key, value in research_counts.items()},
        has_script_variants=script_any,
        has_completed_audit=audit_any,
        has_report=audit_any,
        has_outcomes=outcomes_any,
        next_best_action=next_best_action,
        next_best_href=next_best_href,
        completion_percent=completion_percent,
        stage_completion=stage_completion,
        totals={
            "competitors": sum(competitor_counts.values()),
            "research_items": sum(research_counts.values()),
            "script_variants": script_variant_count,
            "draft_snapshots": draft_snapshot_count,
            "completed_audits": completed_audit_count,
            "outcomes": outcome_count,
        },
        preferred_platform=preferred_platform,
    )
