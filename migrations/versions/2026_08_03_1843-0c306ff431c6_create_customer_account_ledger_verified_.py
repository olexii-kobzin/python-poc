"""create customer_account_ledger_verified table

Revision ID: 0c306ff431c6
Revises: f3bbd6b8a2f1
Create Date: 2026-08-03 18:43:50.101695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c306ff431c6'
down_revision: Union[str, Sequence[str], None] = 'f3bbd6b8a2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('customer_account_ledger_verified',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('through_no', sa.BigInteger(), nullable=False),
        sa.Column('balance', sa.Numeric(precision=16, scale=2, decimal_return_scale=2), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['customer_account.id'], ),
        sa.PrimaryKeyConstraint('id', 'through_no')
    )
    op.create_index('ix_customer_account_ledger_verified_id_verified_at', 'customer_account_ledger_verified', ['id', 'verified_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_customer_account_ledger_verified_id_verified_at', table_name='customer_account_ledger_verified')
    op.drop_table('customer_account_ledger_verified')
