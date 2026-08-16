"""rename ledger id to account_id, fix customer_account constraints

Revision ID: d0b11413183a
Revises: 7b995588da96
Create Date: 2026-08-15 15:15:30.252815

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0b11413183a"
down_revision: str | Sequence[str] | None = "7b995588da96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "customer",
        "status",
        existing_type=sa.TEXT(),
        type_=sa.Enum("ACTIVE", "DISABLED", name="customerstatus", native_enum=False),
        existing_nullable=False,
    )
    op.alter_column(
        "customer_account",
        "status",
        existing_type=sa.TEXT(),
        type_=sa.Enum(
            "ACTIVE",
            "DISABLED",
            "DELETED",
            name="customeraccountstatus",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "customer_account", "updated_by", existing_type=sa.UUID(), nullable=False
    )
    op.drop_constraint(
        op.f("uq_customer_account_id_currency"), "customer_account", type_="unique"
    )
    op.create_unique_constraint(
        "uq_customer_account_customer_id_currency",
        "customer_account",
        ["customer_id", "currency"],
    )
    op.alter_column(
        "customer_account_history",
        "status",
        existing_type=sa.TEXT(),
        type_=sa.Enum(
            "ACTIVE",
            "DISABLED",
            "DELETED",
            name="customeraccountstatus",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "customer_account_history",
        "updated_by",
        existing_type=sa.UUID(),
        nullable=False,
    )
    # autogenerate emitted add+drop for the rename; rewritten to alter_column
    # so the data and the composite PK are kept
    op.alter_column("customer_account_ledger", "id", new_column_name="account_id")
    op.alter_column(
        "customer_account_ledger",
        "operation_type",
        existing_type=sa.TEXT(),
        type_=sa.Enum(
            "CREATE",
            "DEPOSIT",
            "WITHDRAWAL",
            name="ledgeroperationtype",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_id_created_at"),
        table_name="customer_account_ledger",
    )
    op.drop_constraint(
        op.f("uq_customer_account_ledger_id_operation_id"),
        "customer_account_ledger",
        type_="unique",
    )
    op.create_index(
        "ix_customer_account_ledger_account_id_created_at",
        "customer_account_ledger",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_customer_account_ledger_account_id_operation_id",
        "customer_account_ledger",
        ["account_id", "operation_id"],
    )
    op.drop_constraint(
        op.f("fk_customer_account_ledger_id_customer_account_id"),
        "customer_account_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_account_ledger_account_id_customer_account_id",
        "customer_account_ledger",
        "customer_account",
        ["account_id"],
        ["id"],
    )
    op.alter_column(
        "customer_account_ledger_discrepancy", "id", new_column_name="account_id"
    )
    op.alter_column(
        "customer_account_ledger_discrepancy",
        "kind",
        existing_type=sa.TEXT(),
        type_=sa.Enum(
            "ANCHOR_BALANCE",
            "GAP",
            "BALANCE",
            "GAP_BALANCE",
            name="ledgerdiscrepancykind",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.drop_index(
        op.f("uq_customer_account_ledger_discrepancy_open"),
        table_name="customer_account_ledger_discrepancy",
        postgresql_where="(resolved_at IS NULL)",
    )
    op.create_index(
        "uq_customer_account_ledger_discrepancy_open",
        "customer_account_ledger_discrepancy",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        op.f("ix_customer_account_ledger_discrepancy_kind"),
        "customer_account_ledger_discrepancy",
        ["kind"],
        unique=False,
    )
    op.drop_constraint(
        op.f("customer_account_ledger_discrepancy_id_fkey"),
        "customer_account_ledger_discrepancy",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_account_ledger_discrepancy_account_id",
        "customer_account_ledger_discrepancy",
        "customer_account",
        ["account_id"],
        ["id"],
    )
    op.alter_column(
        "customer_account_ledger_verified", "id", new_column_name="account_id"
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_verified_id_verified_at"),
        table_name="customer_account_ledger_verified",
    )
    op.create_index(
        "ix_customer_account_ledger_verified_account_id_verified_at",
        "customer_account_ledger_verified",
        ["account_id", "verified_at"],
        unique=False,
    )
    op.drop_constraint(
        op.f("customer_account_ledger_verified_id_fkey"),
        "customer_account_ledger_verified",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_account_ledger_verified_account_id",
        "customer_account_ledger_verified",
        "customer_account",
        ["account_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "customer_account_ledger_verified", "account_id", new_column_name="id"
    )
    op.drop_constraint(
        "fk_customer_account_ledger_verified_account_id",
        "customer_account_ledger_verified",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("customer_account_ledger_verified_id_fkey"),
        "customer_account_ledger_verified",
        "customer_account",
        ["id"],
        ["id"],
    )
    op.drop_index(
        "ix_customer_account_ledger_verified_account_id_verified_at",
        table_name="customer_account_ledger_verified",
    )
    op.create_index(
        op.f("ix_customer_account_ledger_verified_id_verified_at"),
        "customer_account_ledger_verified",
        ["id", "verified_at"],
        unique=False,
    )
    op.alter_column(
        "customer_account_ledger_discrepancy", "account_id", new_column_name="id"
    )
    op.drop_constraint(
        "fk_customer_account_ledger_discrepancy_account_id",
        "customer_account_ledger_discrepancy",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("customer_account_ledger_discrepancy_id_fkey"),
        "customer_account_ledger_discrepancy",
        "customer_account",
        ["id"],
        ["id"],
    )
    op.drop_index(
        op.f("ix_customer_account_ledger_discrepancy_kind"),
        table_name="customer_account_ledger_discrepancy",
    )
    op.drop_index(
        "uq_customer_account_ledger_discrepancy_open",
        table_name="customer_account_ledger_discrepancy",
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        op.f("uq_customer_account_ledger_discrepancy_open"),
        "customer_account_ledger_discrepancy",
        ["id"],
        unique=True,
        postgresql_where="(resolved_at IS NULL)",
    )
    op.alter_column(
        "customer_account_ledger_discrepancy",
        "kind",
        existing_type=sa.Enum(
            "ANCHOR_BALANCE",
            "GAP",
            "BALANCE",
            "GAP_BALANCE",
            name="ledgerdiscrepancykind",
            native_enum=False,
        ),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
    op.alter_column("customer_account_ledger", "account_id", new_column_name="id")
    op.drop_constraint(
        "fk_customer_account_ledger_account_id_customer_account_id",
        "customer_account_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_customer_account_ledger_id_customer_account_id"),
        "customer_account_ledger",
        "customer_account",
        ["id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_customer_account_ledger_account_id_operation_id",
        "customer_account_ledger",
        type_="unique",
    )
    op.drop_index(
        "ix_customer_account_ledger_account_id_created_at",
        table_name="customer_account_ledger",
    )
    op.create_unique_constraint(
        op.f("uq_customer_account_ledger_id_operation_id"),
        "customer_account_ledger",
        ["id", "operation_id"],
        postgresql_nulls_not_distinct=False,
    )
    op.create_index(
        op.f("ix_customer_account_ledger_id_created_at"),
        "customer_account_ledger",
        ["id", "created_at"],
        unique=False,
    )
    op.alter_column(
        "customer_account_ledger",
        "operation_type",
        existing_type=sa.Enum(
            "CREATE",
            "DEPOSIT",
            "WITHDRAWAL",
            name="ledgeroperationtype",
            native_enum=False,
        ),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
    op.alter_column(
        "customer_account_history", "updated_by", existing_type=sa.UUID(), nullable=True
    )
    op.alter_column(
        "customer_account_history",
        "status",
        existing_type=sa.Enum(
            "ACTIVE",
            "DISABLED",
            "DELETED",
            name="customeraccountstatus",
            native_enum=False,
        ),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
    op.drop_constraint(
        "uq_customer_account_customer_id_currency", "customer_account", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_customer_account_id_currency"),
        "customer_account",
        ["id", "currency"],
        postgresql_nulls_not_distinct=False,
    )
    op.alter_column(
        "customer_account", "updated_by", existing_type=sa.UUID(), nullable=True
    )
    op.alter_column(
        "customer_account",
        "status",
        existing_type=sa.Enum(
            "ACTIVE",
            "DISABLED",
            "DELETED",
            name="customeraccountstatus",
            native_enum=False,
        ),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
    op.alter_column(
        "customer",
        "status",
        existing_type=sa.Enum(
            "ACTIVE", "DISABLED", name="customerstatus", native_enum=False
        ),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
