"""Add subscriptions and usage_events tables for Stripe billing.

Revision ID: 004_billing_tables
Revises: 003_enable_rls
Create Date: 2026-04-11 13:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "004_billing_tables"
down_revision = "003_enable_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("plan", sa.String(length=20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant_id"),
        sa.UniqueConstraint("stripe_subscription_id", name="uq_subscriptions_stripe_sub_id"),
    )
    op.create_index("ix_subscriptions_id", "subscriptions", ["id"])
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index(
        "ix_subscriptions_stripe_customer", "subscriptions", ["stripe_customer_id"]
    )

    # ── usage_events ─────────────────────────────────────────────────────────
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reported_to_stripe", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("stripe_usage_record_id", sa.String(length=64), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_id", "usage_events", ["id"])
    op.create_index("ix_usage_events_tenant_id", "usage_events", ["tenant_id"])
    op.create_index("ix_usage_events_job_id", "usage_events", ["job_id"])
    op.create_index(
        "ix_usage_events_unreported",
        "usage_events",
        ["tenant_id", "reported_to_stripe"],
    )

    # Apply RLS to the new billing tables too.
    conn = op.get_bind()

    for table in ("subscriptions", "usage_events"):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        conn.execute(sa.text(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gem_app"
        ))

    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON SEQUENCE subscriptions_id_seq TO gem_app"
    ))
    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON SEQUENCE usage_events_id_seq TO gem_app"
    ))

    # Seed a free subscription row for each existing tenant (backfill).
    conn.execute(sa.text("""
        INSERT INTO subscriptions (tenant_id, plan, status)
        SELECT DISTINCT tenant_id, 'free', 'active'
        FROM users
        ON CONFLICT (tenant_id) DO NOTHING
    """))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("subscriptions", "usage_events"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_usage_events_unreported", "usage_events")
    op.drop_index("ix_usage_events_job_id", "usage_events")
    op.drop_index("ix_usage_events_tenant_id", "usage_events")
    op.drop_index("ix_usage_events_id", "usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_subscriptions_stripe_customer", "subscriptions")
    op.drop_index("ix_subscriptions_tenant_id", "subscriptions")
    op.drop_index("ix_subscriptions_id", "subscriptions")
    op.drop_table("subscriptions")
