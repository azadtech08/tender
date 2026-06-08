"""Add index on (job_id, gem_position) for fast ordered fetches.

Revision ID: 011_gem_position_index
Revises: 010_gem_order
Create Date: 2026-06-06
"""

from alembic import op

revision = "011_gem_position_index"
down_revision = "010_gem_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tenders_job_gem_position",
        "tenders",
        ["job_id", "gem_position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenders_job_gem_position",
        table_name="tenders",
    )
