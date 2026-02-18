"""add draft snapshots and outcome links

Revision ID: 20260218_000005
Revises: 20260218_000004
Create Date: 2026-02-18 00:00:05.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260218_000005"
down_revision: Union[str, None] = "20260218_000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "draft_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("source_item_id", sa.String(), nullable=True),
        sa.Column("variant_id", sa.String(), nullable=True),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("baseline_score", sa.Float(), nullable=True),
        sa.Column("rescored_score", sa.Float(), nullable=False),
        sa.Column("delta_score", sa.Float(), nullable=True),
        sa.Column("detector_rankings_json", sa.JSON(), nullable=True),
        sa.Column("next_actions_json", sa.JSON(), nullable=True),
        sa.Column("line_level_edits_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["source_item_id"], ["research_items.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_snapshots_user_id", "draft_snapshots", ["user_id"], unique=False)
    op.create_index("ix_draft_snapshots_platform", "draft_snapshots", ["platform"], unique=False)
    op.create_index("ix_draft_snapshots_source_item_id", "draft_snapshots", ["source_item_id"], unique=False)
    op.create_index("ix_draft_snapshots_variant_id", "draft_snapshots", ["variant_id"], unique=False)
    op.create_index("ix_draft_snapshots_created_at", "draft_snapshots", ["created_at"], unique=False)
    op.create_index(
        "ix_draft_snapshots_user_created",
        "draft_snapshots",
        ["user_id", "created_at"],
        unique=False,
    )

    op.add_column("outcome_metrics", sa.Column("draft_snapshot_id", sa.String(), nullable=True))
    op.add_column("outcome_metrics", sa.Column("report_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_outcome_metrics_draft_snapshot_id",
        "outcome_metrics",
        "draft_snapshots",
        ["draft_snapshot_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_outcome_metrics_report_id",
        "outcome_metrics",
        "audits",
        ["report_id"],
        ["id"],
    )
    op.create_index("ix_outcome_metrics_draft_snapshot_id", "outcome_metrics", ["draft_snapshot_id"], unique=False)
    op.create_index("ix_outcome_metrics_report_id", "outcome_metrics", ["report_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outcome_metrics_report_id", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_draft_snapshot_id", table_name="outcome_metrics")
    op.drop_constraint("fk_outcome_metrics_report_id", "outcome_metrics", type_="foreignkey")
    op.drop_constraint("fk_outcome_metrics_draft_snapshot_id", "outcome_metrics", type_="foreignkey")
    op.drop_column("outcome_metrics", "report_id")
    op.drop_column("outcome_metrics", "draft_snapshot_id")

    op.drop_index("ix_draft_snapshots_user_created", table_name="draft_snapshots")
    op.drop_index("ix_draft_snapshots_created_at", table_name="draft_snapshots")
    op.drop_index("ix_draft_snapshots_variant_id", table_name="draft_snapshots")
    op.drop_index("ix_draft_snapshots_source_item_id", table_name="draft_snapshots")
    op.drop_index("ix_draft_snapshots_platform", table_name="draft_snapshots")
    op.drop_index("ix_draft_snapshots_user_id", table_name="draft_snapshots")
    op.drop_table("draft_snapshots")
