"""customer_account_ledger reworked

Revision ID: f3bbd6b8a2f1
Revises: 12138c6b3773
Create Date: 2026-07-29 19:18:22.107938

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3bbd6b8a2f1"
down_revision: str | Sequence[str] | None = "12138c6b3773"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_customer_account_currency"),
        "customer_account",
        ["currency"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_account_status"), "customer_account", ["status"], unique=False
    )

    op.create_index(
        "ix_customer_account_history_currency_history",
        "customer_account_history",
        ["currency"],
        unique=False,
    )
    op.create_index(
        "ix_customer_account_history_status_history",
        "customer_account_history",
        ["status"],
        unique=False,
    )

    op.add_column(
        "customer_account_ledger", sa.Column("no", sa.BigInteger(), nullable=False)
    )
    op.add_column(
        "customer_account_ledger",
        sa.Column(
            "balance",
            sa.Numeric(precision=16, scale=2, decimal_return_scale=2),
            nullable=False,
        ),
    )
    op.add_column(
        "customer_account_ledger", sa.Column("created_by", sa.Uuid(), nullable=True)
    )
    op.drop_constraint(
        "customer_account_ledger_pkey", "customer_account_ledger", type_="primary"
    )
    op.create_primary_key(
        "customer_account_ledger_pkey", "customer_account_ledger", ["id", "no"]
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_created_at"),
        table_name="customer_account_ledger",
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_customer_account_id"),
        table_name="customer_account_ledger",
    )
    op.create_index(
        "ix_customer_account_ledger_id_created_at",
        "customer_account_ledger",
        ["id", "created_at"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_customer_account_ledger_id_operation_id",
        "customer_account_ledger",
        ["id", "operation_id"],
    )
    op.drop_constraint(
        op.f("customer_account_ledger_customer_account_id_fkey"),
        "customer_account_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_account_ledger_id_customer_account_id",
        "customer_account_ledger",
        "customer_account",
        ["id"],
        ["id"],
    )
    op.drop_column("customer_account_ledger", "customer_account_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "customer_account_ledger",
        sa.Column(
            "customer_account_id", sa.UUID(), autoincrement=False, nullable=False
        ),
    )
    op.drop_constraint(
        "fk_customer_account_ledger_id_customer_account_id",
        "customer_account_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("customer_account_ledger_customer_account_id_fkey"),
        "customer_account_ledger",
        "customer_account",
        ["customer_account_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_customer_account_ledger_id_operation_id",
        "customer_account_ledger",
        type_="unique",
    )
    op.drop_index(
        "ix_customer_account_ledger_id_created_at", table_name="customer_account_ledger"
    )
    op.create_index(
        op.f("ix_customer_account_ledger_customer_account_id"),
        "customer_account_ledger",
        ["customer_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_account_ledger_created_at"),
        "customer_account_ledger",
        ["created_at"],
        unique=False,
    )
    op.drop_constraint(
        "customer_account_ledger_pkey", "customer_account_ledger", type_="primary"
    )
    op.create_primary_key(
        "customer_account_ledger_pkey", "customer_account_ledger", ["id"]
    )
    op.drop_column("customer_account_ledger", "created_by")
    op.drop_column("customer_account_ledger", "balance")
    op.drop_column("customer_account_ledger", "no")

    op.drop_index(
        "ix_customer_account_history_status_history",
        table_name="customer_account_history",
    )
    op.drop_index(
        "ix_customer_account_history_currency_history",
        table_name="customer_account_history",
    )

    op.drop_index(op.f("ix_customer_account_status"), table_name="customer_account")
    op.drop_index(op.f("ix_customer_account_currency"), table_name="customer_account")
