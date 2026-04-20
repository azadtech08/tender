"""Add tenant_id to jobs and tenders tables for multi-tenancy

Revision ID: 002_add_tenant_id
Revises: 001_initial_schema
Create Date: 2026-04-11 12:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_tenant_id'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tenant_id to jobs table
    op.add_column(
        'jobs',
        sa.Column('tenant_id', sa.String(length=36), nullable=False, server_default='00000000-0000-0000-0000-000000000000')
    )
    op.create_index('ix_jobs_tenant_id', 'jobs', ['tenant_id'])
    op.create_index('ix_jobs_tenant_id_user_id', 'jobs', ['tenant_id', 'user_id'])
    
    # Remove server default after populating
    op.alter_column('jobs', 'tenant_id', server_default=None)
    
    # Add tenant_id to tenders table
    op.add_column(
        'tenders',
        sa.Column('tenant_id', sa.String(length=36), nullable=False, server_default='00000000-0000-0000-0000-000000000000')
    )
    op.create_index('ix_tenders_tenant_id', 'tenders', ['tenant_id'])
    op.create_index('ix_tenders_tenant_id_keyword', 'tenders', ['tenant_id', 'keyword'])
    
    # Remove server default after populating
    op.alter_column('tenders', 'tenant_id', server_default=None)


def downgrade() -> None:
    # Drop indices
    op.drop_index('ix_tenders_tenant_id_keyword', 'tenders')
    op.drop_index('ix_tenders_tenant_id', 'tenders')
    op.drop_index('ix_jobs_tenant_id_user_id', 'jobs')
    op.drop_index('ix_jobs_tenant_id', 'jobs')
    
    # Drop columns
    op.drop_column('tenders', 'tenant_id')
    op.drop_column('jobs', 'tenant_id')
