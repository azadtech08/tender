"""Add phonepe_transactions table for PhonePe payment gateway.

Revision ID: 009_phonepe_transactions
Revises: 008_make_user_id_nullable
Create Date: 2026-04-29 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "009_phonepe_transactions"
down_revision = "008_make_user_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phonepe_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("merchant_transaction_id", sa.String(length=38), nullable=False),
        sa.Column("phonepe_transaction_id", sa.String(length=64), nullable=True),
        sa.Column(
            "payment_status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("payment_method", sa.String(length=50), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "merchant_transaction_id",
            name="uq_phonepe_transactions_merchant_txn_id",
        ),
    )
    op.create_index(
        "ix_phonepe_transactions_id", "phonepe_transactions", ["id"]
    )
    op.create_index(
        "ix_phonepe_transactions_tenant_id", "phonepe_transactions", ["tenant_id"]
    )
    op.create_index(
        "ix_phonepe_transactions_merchant_transaction_id",
        "phonepe_transactions",
        ["merchant_transaction_id"],
    )
    op.create_index(
        "ix_phonepe_transactions_tenant_status",
        "phonepe_transactions",
        ["tenant_id", "payment_status"],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text("ALTER TABLE phonepe_transactions ENABLE ROW LEVEL SECURITY")
    )
    conn.execute(
        sa.text(
            "DROP POLICY IF EXISTS tenant_isolation ON phonepe_transactions"
        )
    )
    conn.execute(sa.text("""
        CREATE POLICY tenant_isolation ON phonepe_transactions
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
    """))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON phonepe_transactions TO gem_app"
    ))
    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON SEQUENCE phonepe_transactions_id_seq TO gem_app"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DROP POLICY IF EXISTS tenant_isolation ON phonepe_transactions"
        )
    )
    conn.execute(
        sa.text("ALTER TABLE phonepe_transactions DISABLE ROW LEVEL SECURITY")
    )
    op.drop_index(
        "ix_phonepe_transactions_tenant_status", "phonepe_transactions"
    )
    op.drop_index(
        "ix_phonepe_transactions_merchant_transaction_id",
        "phonepe_transactions",
    )
    op.drop_index(
        "ix_phonepe_transactions_tenant_id", "phonepe_transactions"
    )
    op.drop_index("ix_phonepe_transactions_id", "phonepe_transactions")
    op.drop_table("phonepe_transactions")
