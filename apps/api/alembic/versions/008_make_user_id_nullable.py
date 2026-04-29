"""Make user_id nullable in jobs table

Revision ID: 008_make_user_id_nullable
Revises: 007_admin_audit_clerk_compat
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_make_user_id_nullable'
down_revision = '007_admin_audit_clerk_compat'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make user_id nullable since we're moving to tenant_id-based ownership
    # The legacy user_id FK is being dropped in favor of tenant_id
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Revert to not nullable
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)