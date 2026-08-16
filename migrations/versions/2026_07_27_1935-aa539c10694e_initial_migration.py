"""initial migration

Revision ID: aa539c10694e
Revises:
Create Date: 2026-07-27 19:35:17.108158

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aa539c10694e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "customer",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(
        op.f("ix_customer_created_at"), "customer", ["created_at"], unique=False
    )

    op.create_table(
        "customer_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
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
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customer_account_created_at"),
        "customer_account",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_account_customer_id"),
        "customer_account",
        ["customer_id"],
        unique=False,
    )

    op.create_table(
        "customer_account_history",
        sa.Column("id", sa.Uuid(), autoincrement=False, nullable=False),
        sa.Column("customer_id", sa.Uuid(), autoincrement=False, nullable=False),
        sa.Column("currency", sa.Text(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), autoincrement=False, nullable=True),
        sa.Column("status", sa.Text(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("updated_by", sa.Uuid(), autoincrement=False, nullable=True),
        sa.Column("version", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
        ),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.create_index(
        "ix_customer_account_history_created_at_history",
        "customer_account_history",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_customer_account_history_customer_id_history",
        "customer_account_history",
        ["customer_id"],
        unique=False,
    )

    op.create_table(
        "customer_account_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "amount",
            sa.Numeric(precision=16, scale=2, decimal_return_scale=2),
            nullable=False,
        ),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_account.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customer_account_ledger_created_at"),
        "customer_account_ledger",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_account_ledger_customer_account_id"),
        "customer_account_ledger",
        ["customer_account_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_customer_account_ledger_customer_account_id"),
        table_name="customer_account_ledger",
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_created_at"),
        table_name="customer_account_ledger",
    )
    op.drop_table("customer_account_ledger")
    op.drop_index(
        "ix_customer_account_history_customer_id_history",
        table_name="customer_account_history",
    )
    op.drop_index(
        "ix_customer_account_history_created_at_history",
        table_name="customer_account_history",
    )
    op.drop_table("customer_account_history")
    op.drop_index(
        op.f("ix_customer_account_customer_id"), table_name="customer_account"
    )
    op.drop_index(op.f("ix_customer_account_created_at"), table_name="customer_account")
    op.drop_table("customer_account")
    op.drop_index(op.f("ix_customer_created_at"), table_name="customer")
    op.drop_table("customer")
