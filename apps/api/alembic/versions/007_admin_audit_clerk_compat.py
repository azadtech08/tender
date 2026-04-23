"""Make admin_audit_log work for Clerk-authenticated admins.

Revision ID: 007_admin_audit_clerk_compat
Revises: 006_licensing
Create Date: 2026-04-22

Phase 2 modelled admin_id as a NOT NULL FK to users.id, but Clerk users
don't have local users rows (the local User table is for HS256 local auth
only). To support both:

  - admin_id becomes NULLABLE (still FK to users.id when known)
  - admin_subject (NOT NULL) carries the auth-provider subject —
    a Clerk user_id like 'user_2abc...' or a stringified local users.id
  - admin_email (NULL) carries the email at write-time for display

This is purely additive + a nullability relaxation; no data loss.
"""

from alembic import op
import sqlalchemy as sa

revision = "007_admin_audit_clerk_compat"
down_revision = "006_licensing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "admin_audit_log",
        "admin_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "admin_audit_log",
        sa.Column(
            "admin_subject",
            sa.String(64),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "admin_audit_log",
        sa.Column("admin_email", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_admin_audit_subject_created",
        "admin_audit_log",
        ["admin_subject", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_subject_created", table_name="admin_audit_log"
    )
    op.drop_column("admin_audit_log", "admin_email")
    op.drop_column("admin_audit_log", "admin_subject")
    op.alter_column(
        "admin_audit_log",
        "admin_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
