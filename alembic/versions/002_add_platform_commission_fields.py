"""Add platform commission fields

Revision ID: 002_add_platform_commission_fields
Revises: c2a8b_add_stripe_columns_to_drivers
Create Date: 2025-01-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_platform_commission_fields'
down_revision = 'c2a8b_add_stripe_columns_to_drivers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add platform commission fields to payments table
    op.add_column('payments', sa.Column('total_amount', sa.DECIMAL(10, 2), nullable=True))
    op.add_column('payments', sa.Column('driver_amount', sa.DECIMAL(10, 2), nullable=True))
    op.add_column('payments', sa.Column('platform_fee', sa.DECIMAL(10, 2), nullable=True))
    
    # Update currency default from EUR to GBP
    op.alter_column('payments', 'currency', server_default='GBP')
    
    # Add platform commission fields to driver_earnings table
    op.add_column('driver_earnings', sa.Column('total_job_amount', sa.DECIMAL(10, 2), nullable=True))
    op.add_column('driver_earnings', sa.Column('platform_fee', sa.DECIMAL(10, 2), nullable=True))


def downgrade() -> None:
    # Remove platform commission fields from driver_earnings table
    op.drop_column('driver_earnings', 'platform_fee')
    op.drop_column('driver_earnings', 'total_job_amount')
    
    # Revert currency default back to EUR
    op.alter_column('payments', 'currency', server_default='EUR')
    
    # Remove platform commission fields from payments table
    op.drop_column('payments', 'platform_fee')
    op.drop_column('payments', 'driver_amount')
    op.drop_column('payments', 'total_amount')