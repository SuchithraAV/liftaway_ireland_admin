"""add_stripe_columns_to_drivers

Revision ID: c2a8b
Revises: b5e55d2eabc8
Create Date: 2025-12-10 22:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c2a8b'
down_revision = 'b5e55d2eabc8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Stripe related columns to drivers table
    op.add_column('drivers', sa.Column('stripe_account_id', sa.String(length=255), nullable=True))
    op.add_column('drivers', sa.Column('stripe_verification_status', sa.String(length=50), nullable=True, server_default='pending'))
    op.add_column('drivers', sa.Column('stripe_payouts_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.add_column('drivers', sa.Column('stripe_bank_last4', sa.String(length=4), nullable=True))


def downgrade() -> None:
    op.drop_column('drivers', 'stripe_bank_last4')
    op.drop_column('drivers', 'stripe_payouts_enabled')
    op.drop_column('drivers', 'stripe_verification_status')
    op.drop_column('drivers', 'stripe_account_id')
