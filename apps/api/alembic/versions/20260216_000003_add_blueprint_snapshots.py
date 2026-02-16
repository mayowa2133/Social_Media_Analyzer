"""add blueprint snapshots cache table

Revision ID: 20260216_000003
Revises: 20260214_000002
Create Date: 2026-02-16 00:00:03.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260216_000003"
down_revision: Union[str, None] = "20260214_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blueprint_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("competitor_signature", sa.String(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_blueprint_snapshots_user_id",
        "blueprint_snapshots",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_blueprint_snapshots_user_id", table_name="blueprint_snapshots")
    op.drop_table("blueprint_snapshots")
