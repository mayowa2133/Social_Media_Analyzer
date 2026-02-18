"""add research, optimizer, outcomes, credits, and share-link tables

Revision ID: 20260218_000004
Revises: 20260216_000003
Create Date: 2026-02-18 00:00:04.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260218_000004"
down_revision: Union[str, None] = "20260216_000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_collections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_collections_user_id", "research_collections", ["user_id"], unique=False)

    op.create_table(
        "research_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("collection_id", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("creator_handle", sa.String(), nullable=True),
        sa.Column("creator_display_name", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("media_meta_json", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["research_collections.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_items_user_id", "research_items", ["user_id"], unique=False)
    op.create_index("ix_research_items_collection_id", "research_items", ["collection_id"], unique=False)
    op.create_index("ix_research_items_platform", "research_items", ["platform"], unique=False)
    op.create_index("ix_research_items_external_id", "research_items", ["external_id"], unique=False)
    op.create_index("ix_research_items_creator_handle", "research_items", ["creator_handle"], unique=False)
    op.create_index("ix_research_items_created_at", "research_items", ["created_at"], unique=False)
    op.create_index(
        "ix_research_items_user_platform_created",
        "research_items",
        ["user_id", "platform", "created_at"],
        unique=False,
    )

    op.create_table(
        "script_variants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_item_id", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("variants_json", sa.JSON(), nullable=False),
        sa.Column("selected_variant_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["source_item_id"], ["research_items.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_script_variants_user_id", "script_variants", ["user_id"], unique=False)
    op.create_index("ix_script_variants_source_item_id", "script_variants", ["source_item_id"], unique=False)
    op.create_index("ix_script_variants_platform", "script_variants", ["platform"], unique=False)
    op.create_index("ix_script_variants_created_at", "script_variants", ["created_at"], unique=False)

    op.create_table(
        "outcome_metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("content_item_id", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("video_external_id", sa.String(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_metrics_json", sa.JSON(), nullable=False),
        sa.Column("retention_points_json", sa.JSON(), nullable=True),
        sa.Column("predicted_score", sa.Float(), nullable=True),
        sa.Column("actual_score", sa.Float(), nullable=True),
        sa.Column("calibration_delta", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["content_item_id"], ["research_items.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outcome_metrics_user_id", "outcome_metrics", ["user_id"], unique=False)
    op.create_index("ix_outcome_metrics_content_item_id", "outcome_metrics", ["content_item_id"], unique=False)
    op.create_index("ix_outcome_metrics_platform", "outcome_metrics", ["platform"], unique=False)
    op.create_index("ix_outcome_metrics_video_external_id", "outcome_metrics", ["video_external_id"], unique=False)
    op.create_index("ix_outcome_metrics_created_at", "outcome_metrics", ["created_at"], unique=False)
    op.create_index(
        "ix_outcome_metrics_user_platform_created",
        "outcome_metrics",
        ["user_id", "platform", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_outcome_metrics_content_item_lookup",
        "outcome_metrics",
        ["content_item_id"],
        unique=False,
    )

    op.create_table(
        "calibration_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mean_abs_error", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hit_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trend", sa.String(), nullable=False, server_default="flat"),
        sa.Column("recommendations_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calibration_snapshots_user_id", "calibration_snapshots", ["user_id"], unique=False)
    op.create_index("ix_calibration_snapshots_platform", "calibration_snapshots", ["platform"], unique=False)
    op.create_index(
        "ix_calibration_snapshots_user_platform",
        "calibration_snapshots",
        ["user_id", "platform"],
        unique=True,
    )

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("delta_credits", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("reference_type", sa.String(), nullable=True),
        sa.Column("reference_id", sa.String(), nullable=True),
        sa.Column("billing_provider", sa.String(), nullable=True),
        sa.Column("billing_reference", sa.String(), nullable=True),
        sa.Column("period_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"], unique=False)
    op.create_index("ix_credit_ledger_created_at", "credit_ledger", ["created_at"], unique=False)
    op.create_index("ix_credit_ledger_period_key", "credit_ledger", ["period_key"], unique=False)
    op.create_index(
        "ix_credit_ledger_user_created",
        "credit_ledger",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_credit_ledger_user_period",
        "credit_ledger",
        ["user_id", "period_key"],
        unique=False,
    )

    op.create_table(
        "report_share_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("audit_id", sa.String(), nullable=False),
        sa.Column("share_token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["audit_id"], ["audits.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_token"),
    )
    op.create_index("ix_report_share_links_user_id", "report_share_links", ["user_id"], unique=False)
    op.create_index("ix_report_share_links_audit_id", "report_share_links", ["audit_id"], unique=False)
    op.create_index("ix_report_share_links_share_token", "report_share_links", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_report_share_links_share_token", table_name="report_share_links")
    op.drop_index("ix_report_share_links_audit_id", table_name="report_share_links")
    op.drop_index("ix_report_share_links_user_id", table_name="report_share_links")
    op.drop_table("report_share_links")

    op.drop_index("ix_credit_ledger_user_period", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_user_created", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_period_key", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_created_at", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_user_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")

    op.drop_index("ix_calibration_snapshots_user_platform", table_name="calibration_snapshots")
    op.drop_index("ix_calibration_snapshots_platform", table_name="calibration_snapshots")
    op.drop_index("ix_calibration_snapshots_user_id", table_name="calibration_snapshots")
    op.drop_table("calibration_snapshots")

    op.drop_index("ix_outcome_metrics_content_item_lookup", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_user_platform_created", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_created_at", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_video_external_id", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_platform", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_content_item_id", table_name="outcome_metrics")
    op.drop_index("ix_outcome_metrics_user_id", table_name="outcome_metrics")
    op.drop_table("outcome_metrics")

    op.drop_index("ix_script_variants_created_at", table_name="script_variants")
    op.drop_index("ix_script_variants_platform", table_name="script_variants")
    op.drop_index("ix_script_variants_source_item_id", table_name="script_variants")
    op.drop_index("ix_script_variants_user_id", table_name="script_variants")
    op.drop_table("script_variants")

    op.drop_index("ix_research_items_user_platform_created", table_name="research_items")
    op.drop_index("ix_research_items_created_at", table_name="research_items")
    op.drop_index("ix_research_items_creator_handle", table_name="research_items")
    op.drop_index("ix_research_items_external_id", table_name="research_items")
    op.drop_index("ix_research_items_platform", table_name="research_items")
    op.drop_index("ix_research_items_collection_id", table_name="research_items")
    op.drop_index("ix_research_items_user_id", table_name="research_items")
    op.drop_table("research_items")

    op.drop_index("ix_research_collections_user_id", table_name="research_collections")
    op.drop_table("research_collections")
