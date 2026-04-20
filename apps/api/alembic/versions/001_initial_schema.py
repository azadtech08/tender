"""Initial schema creation — all 5 core tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-04-11 11:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'])
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'])

    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('cards_per_kw', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('min_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('total_keywords', sa.Integer(), nullable=True),
        sa.Column('done_keywords', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_tenders', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_user_id_status', 'jobs', ['user_id', 'status'])
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'])
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'])
    op.create_index(op.f('ix_jobs_user_id'), 'jobs', ['user_id'])
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'])

    # Create job_events table
    op.create_table(
        'job_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_job_events_job_id_created_at', 'job_events', ['job_id', 'created_at'])
    op.create_index(op.f('ix_job_events_id'), 'job_events', ['id'])
    op.create_index(op.f('ix_job_events_job_id'), 'job_events', ['job_id'])

    # Create tenders table
    op.create_table(
        'tenders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('keyword', sa.String(length=255), nullable=False),
        sa.Column('tender_ref_no', sa.String(length=100), nullable=False),
        sa.Column('tender_type', sa.String(length=50), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('bid_end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cleaned_boq', sa.Text(), nullable=True),
        sa.Column('organisation', sa.String(length=500), nullable=True),
        sa.Column('ministry', sa.String(length=500), nullable=True),
        sa.Column('tender_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('emd', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('pincode', sa.String(length=10), nullable=True),
        sa.Column('delivery_period', sa.String(length=100), nullable=True),
        sa.Column('product_type', sa.String(length=100), nullable=True),
        sa.Column('exemption', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('it_relevant', sa.String(length=10), nullable=True),
        sa.Column('quantity', sa.String(length=255), nullable=True),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('scraped_date', sa.Date(), nullable=True),
        sa.Column('pdf_s3_key', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_tenders_ref_job', 'tenders', ['tender_ref_no', 'job_id'], unique=True)
    op.create_index('ix_tenders_job_id_keyword', 'tenders', ['job_id', 'keyword'])
    op.create_index(op.f('ix_tenders_scraped_date'), 'tenders', ['scraped_date'])
    op.create_index(op.f('ix_tenders_id'), 'tenders', ['id'])
    op.create_index(op.f('ix_tenders_job_id'), 'tenders', ['job_id'])
    op.create_index(op.f('ix_tenders_keyword'), 'tenders', ['keyword'])

    # Create schedules table
    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('cron_hour', sa.Integer(), nullable=False, server_default='9'),
        sa.Column('cron_minute', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index('ix_schedules_job_id_is_active', 'schedules', ['job_id', 'is_active'])
    op.create_index(op.f('ix_schedules_id'), 'schedules', ['id'])
    op.create_index(op.f('ix_schedules_job_id'), 'schedules', ['job_id'])


def downgrade() -> None:
    # Drop tables in reverse order (due to FK dependencies)
    op.drop_table('schedules')
    op.drop_table('tenders')
    op.drop_table('job_events')
    op.drop_table('jobs')
    op.drop_table('users')
