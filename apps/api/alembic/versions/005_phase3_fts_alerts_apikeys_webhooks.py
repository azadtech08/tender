"""Phase 3: FTS search_vector, alerts, api_keys, outbound_webhooks.

Revision ID: 005
Revises: 004_billing_tables
Create Date: 2026-04-14

Changes:
  1. Add search_vector tsvector column to tenders + GIN index + auto-update trigger
  2. Create alerts table
  3. Create alert_deliveries table
  4. Create api_keys table
  5. Create outbound_webhooks table
  6. Create webhook_deliveries table
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004_billing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. search_vector on tenders ─────────────────────────────────────────

    op.add_column(
        "tenders",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            nullable=True,
        ),
    )

    # GIN index for fast FTS
    op.create_index(
        "ix_tenders_search_vector",
        "tenders",
        ["search_vector"],
        postgresql_using="gin",
    )

    # Trigger function: auto-update search_vector on INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION tenders_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.cleaned_boq, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.organisation, '')), 'C') ||
                setweight(to_tsvector('english', coalesce(NEW.ministry, '')), 'C') ||
                setweight(to_tsvector('english', coalesce(NEW.keyword, '')), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER tenders_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, description, cleaned_boq, organisation, ministry, keyword
        ON tenders
        FOR EACH ROW EXECUTE FUNCTION tenders_search_vector_update();
    """)

    # Backfill existing rows
    op.execute("""
        UPDATE tenders SET search_vector =
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(cleaned_boq, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(organisation, '')), 'C') ||
            setweight(to_tsvector('english', coalesce(ministry, '')), 'C') ||
            setweight(to_tsvector('english', coalesce(keyword, '')), 'D');
    """)

    # ── 2. alerts ───────────────────────────────────────────────────────────

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("min_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("state_filter", sa.String(100), nullable=True),
        sa.Column("email_to", sa.String(255), nullable=True),
        sa.Column("slack_webhook_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_tenant_active", "alerts", ["tenant_id", "is_active"])
    op.create_index("ix_alerts_id", "alerts", ["id"])

    # ── 3. alert_deliveries ─────────────────────────────────────────────────

    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tenders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_deliveries_alert_id", "alert_deliveries", ["alert_id"])

    # ── 4. api_keys ──────────────────────────────────────────────────────────

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_tenant_active", "api_keys", ["tenant_id", "is_active"])

    # ── 5. outbound_webhooks ─────────────────────────────────────────────────

    op.create_table(
        "outbound_webhooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("events", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_webhooks_tenant", "outbound_webhooks", ["tenant_id", "is_active"])

    # ── 6. webhook_deliveries ────────────────────────────────────────────────

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_id", sa.Integer(), sa.ForeignKey("outbound_webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])

    # ── 7. RLS on Phase 3 tenant-scoped tables ───────────────────────────────
    for tbl in ("alerts", "api_keys", "outbound_webhooks"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {tbl}
            USING (
                tenant_id = current_setting('app.tenant_id', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.tenant_id', true)
            )
        """)


def downgrade() -> None:
    for tbl in ("alerts", "api_keys", "outbound_webhooks"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")

    op.drop_table("webhook_deliveries")
    op.drop_table("outbound_webhooks")
    op.drop_table("api_keys")
    op.drop_table("alert_deliveries")
    op.drop_table("alerts")

    op.execute("DROP TRIGGER IF EXISTS tenders_search_vector_trigger ON tenders;")
    op.execute("DROP FUNCTION IF EXISTS tenders_search_vector_update();")
    op.drop_index("ix_tenders_search_vector", table_name="tenders")
    op.drop_column("tenders", "search_vector")
