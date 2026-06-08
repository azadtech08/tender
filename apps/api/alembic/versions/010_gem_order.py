"""Add gem_position to tenders and sort_preference to jobs.

Revision ID: 010_gem_order
Revises: 009_phonepe_transactions
Create Date: 2026-06-05 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "010_gem_order"
down_revision = "009_phonepe_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenders",
        sa.Column("gem_position", sa.Integer(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "sort_preference",
            sa.String(30),
            nullable=True,
            server_default="bid_end_latest",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "sort_preference")
    op.drop_column("tenders", "gem_position")
