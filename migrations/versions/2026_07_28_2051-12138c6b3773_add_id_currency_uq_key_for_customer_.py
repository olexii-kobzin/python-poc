"""add id, currency uq key for customer_account

Revision ID: 12138c6b3773
Revises: aa539c10694e
Create Date: 2026-07-28 20:51:59.769120

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "12138c6b3773"
down_revision: str | Sequence[str] | None = "aa539c10694e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_customer_account_id_currency", "customer_account", ["id", "currency"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_customer_account_id_currency", "customer_account", type_="unique"
    )
