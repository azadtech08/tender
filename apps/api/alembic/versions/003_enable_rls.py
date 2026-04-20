"""Enable Row-Level Security on tenant-scoped tables.

Revision ID: 003_enable_rls
Revises: 002_add_tenant_id
Create Date: 2026-04-11 13:00:00

RLS design:
  - Each tenant-scoped table has a policy that restricts rows to
    current_setting('app.tenant_id', true).
  - The migration user is a superuser and bypasses RLS (FORCE ROW SECURITY
    is NOT set — migrations run as superuser).
  - Application connects as role 'gem_app' which has RLS enforced.
  - A permissive bypass setting: when app.tenant_id is empty (health checks,
    internal tooling), no rows are visible — this is intentional and safe.
"""

from alembic import op
import sqlalchemy as sa

revision = "003_enable_rls"
down_revision = "002_add_tenant_id"
branch_labels = None
depends_on = None

# Tables that carry tenant_id and should be RLS-protected.
TENANT_TABLES = ["jobs", "tenders"]


def upgrade() -> None:
    conn = op.get_bind()

    # Create a dedicated application role that has RLS enforced.
    # The superuser (postgres / gem) bypasses RLS automatically.
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gem_app') THEN
                CREATE ROLE gem_app LOGIN PASSWORD 'gem_app_devpass';
            END IF;
        END$$;
    """))

    # Grant the app role access to the schema and all current + future tables.
    conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO gem_app"))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gem_app"
    ))
    conn.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gem_app"
    ))
    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gem_app"
    ))
    conn.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO gem_app"
    ))

    for table in TENANT_TABLES:
        # Enable RLS on the table.
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))

        # Drop policy if it exists (idempotent re-runs).
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
        ))

        # Permissive SELECT / INSERT / UPDATE / DELETE policy:
        # Row is visible / writable only when its tenant_id matches the
        # session-level setting app.tenant_id.
        conn.execute(sa.text(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                tenant_id = current_setting('app.tenant_id', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.tenant_id', true)
            )
        """))

    # users table: each user sees only their own row.
    conn.execute(sa.text("ALTER TABLE users ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("DROP POLICY IF EXISTS user_self ON users"))
    conn.execute(sa.text("""
        CREATE POLICY user_self ON users
        USING (
            tenant_id = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            tenant_id = current_setting('app.tenant_id', true)
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()

    for table in TENANT_TABLES + ["users"]:  # noqa: E501 — job_events/schedules excluded (no tenant_id col)
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
        ))
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS user_self ON {table}"
        ))
        conn.execute(sa.text(
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
        ))
