"""Phase 2 licensing: licenses, devices, activations, usage counters, admin audit log.

Revision ID: 006_licensing
Revises: 005
Create Date: 2026-04-22

Adds five tables:
  1. licenses                   — one row per tenant license (RLS)
  2. license_devices            — devices/installs bound to a license (RLS)
  3. license_activations        — append-only audit of activate/heartbeat/denied events (RLS)
  4. license_usage_counters     — per-license daily/monthly usage tallies (RLS)
  5. admin_audit_log            — cross-tenant admin action trail (NOT RLS — admin-only)

RLS policies follow migration 003's pattern: a tenant_isolation policy on
each tenant-scoped table, using current_setting('app.tenant_id', true).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_licensing"
down_revision = "005"
branch_labels = None
depends_on = None

# Tenant-scoped tables (RLS enabled). admin_audit_log is intentionally excluded.
TENANT_TABLES = [
    "licenses",
    "license_devices",
    "license_activations",
    "license_usage_counters",
]


def upgrade() -> None:
    # ── 1. licenses ─────────────────────────────────────────────────────────
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("signing_kid", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "features",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("fingerprint_salt", sa.String(128), nullable=False),
        sa.Column(
            "issued_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_licenses_key_hash"),
    )
    op.create_index("ix_licenses_id", "licenses", ["id"])
    op.create_index("ix_licenses_tenant_id", "licenses", ["tenant_id"])
    op.create_index("ix_licenses_tenant_status", "licenses", ["tenant_id", "status"])
    op.create_index("ix_licenses_expires_at", "licenses", ["expires_at"])

    # ── 2. license_devices ──────────────────────────────────────────────────
    op.create_table(
        "license_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_ip", sa.String(45), nullable=True),
        sa.Column("last_user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_license_devices_id", "license_devices", ["id"])
    op.create_index("ix_license_devices_tenant_id", "license_devices", ["tenant_id"])
    op.create_index("ix_license_devices_license_id", "license_devices", ["license_id"])
    op.create_index(
        "ix_license_devices_unique_fp",
        "license_devices",
        ["license_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_license_devices_last_seen", "license_devices", ["last_seen_at"]
    )

    # ── 3. license_activations ──────────────────────────────────────────────
    op.create_table(
        "license_activations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(128), nullable=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_license_activations_tenant_id", "license_activations", ["tenant_id"]
    )
    op.create_index(
        "ix_license_activations_license_created",
        "license_activations",
        ["license_id", "created_at"],
    )
    op.create_index(
        "ix_license_activations_tenant_created",
        "license_activations",
        ["tenant_id", "created_at"],
    )

    # ── 4. license_usage_counters ───────────────────────────────────────────
    op.create_table(
        "license_usage_counters",
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("counter_name", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("license_id", "period_start", "counter_name"),
    )
    op.create_index(
        "ix_license_usage_tenant_id", "license_usage_counters", ["tenant_id"]
    )
    op.create_index(
        "ix_license_usage_tenant_period",
        "license_usage_counters",
        ["tenant_id", "period_start"],
    )

    # ── 5. admin_audit_log ──────────────────────────────────────────────────
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "admin_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_tenant_id", sa.String(36), nullable=True),
        sa.Column(
            "target_license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_admin_created",
        "admin_audit_log",
        ["admin_id", "created_at"],
    )
    op.create_index(
        "ix_admin_audit_target_license",
        "admin_audit_log",
        ["target_license_id"],
    )
    op.create_index(
        "ix_admin_audit_target_tenant_created",
        "admin_audit_log",
        ["target_tenant_id", "created_at"],
    )

    # ── RLS on tenant-scoped tables ─────────────────────────────────────────
    conn = op.get_bind()
    for table in TENANT_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        )
        conn.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (
                    tenant_id = current_setting('app.tenant_id', true)
                )
                WITH CHECK (
                    tenant_id = current_setting('app.tenant_id', true)
                )
                """
            )
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop RLS policies first
    for table in TENANT_TABLES:
        conn.execute(
            sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        )
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    # Drop tables in reverse FK order: admin_audit_log references licenses,
    # usage_counters/activations/devices reference licenses, licenses references users.
    op.drop_table("admin_audit_log")
    op.drop_table("license_usage_counters")
    op.drop_table("license_activations")
    op.drop_table("license_devices")
    op.drop_table("licenses")
