"""Increase column sizes for encryption

Revision ID: 017_increase_column_sizes
Revises: 
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa


revision = '017_increase_column_sizes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Increase column sizes to accommodate encrypted data
    # Encrypted data is ~3x larger than plaintext
    
    # Customers table
    op.alter_column('customers', 'phone_number', type_=sa.String(500), existing_type=sa.String(20))
    op.alter_column('customers', 'email', type_=sa.String(500), existing_type=sa.String(255))
    op.alter_column('customers', 'full_name', type_=sa.String(500), existing_type=sa.String(255))
    op.alter_column('customers', 'address', type_=sa.Text(), existing_type=sa.Text())
    
    # Drivers table
    op.alter_column('drivers', 'phone_number', type_=sa.String(500), existing_type=sa.String(20))
    op.alter_column('drivers', 'email', type_=sa.String(500), existing_type=sa.String(255))
    op.alter_column('drivers', 'full_name', type_=sa.String(500), existing_type=sa.String(255))
    op.alter_column('drivers', 'address', type_=sa.Text(), existing_type=sa.Text())
    
    # Admins table
    op.alter_column('admins', 'phone_number', type_=sa.String(500), existing_type=sa.String(20))
    
    # Driver bank details
    op.alter_column('driver_bank_details', 'bank_account_number', type_=sa.String(500), existing_type=sa.String(100))
    op.alter_column('driver_bank_details', 'bank_ifsc', type_=sa.String(500), existing_type=sa.String(20))
    op.alter_column('driver_bank_details', 'account_holder_name', type_=sa.String(500), existing_type=sa.String(200))
    op.alter_column('driver_bank_details', 'upi_id', type_=sa.String(500), existing_type=sa.String(100))
    
    # Driver documents
    op.alter_column('driver_documents', 'govt_id_number', type_=sa.String(500), existing_type=sa.String(100))
    op.alter_column('driver_documents', 'license_number', type_=sa.String(500), existing_type=sa.String(100))


def downgrade():
    # Revert column sizes (WARNING: may truncate data!)
    op.alter_column('customers', 'phone_number', type_=sa.String(20), existing_type=sa.String(500))
    op.alter_column('customers', 'email', type_=sa.String(255), existing_type=sa.String(500))
    op.alter_column('customers', 'full_name', type_=sa.String(255), existing_type=sa.String(500))
    
    op.alter_column('drivers', 'phone_number', type_=sa.String(20), existing_type=sa.String(500))
    op.alter_column('drivers', 'email', type_=sa.String(255), existing_type=sa.String(500))
    op.alter_column('drivers', 'full_name', type_=sa.String(255), existing_type=sa.String(500))
    
    op.alter_column('admins', 'phone_number', type_=sa.String(20), existing_type=sa.String(500))
    
    op.alter_column('driver_bank_details', 'bank_account_number', type_=sa.String(100), existing_type=sa.String(500))
    op.alter_column('driver_bank_details', 'bank_ifsc', type_=sa.String(20), existing_type=sa.String(500))
    op.alter_column('driver_bank_details', 'account_holder_name', type_=sa.String(200), existing_type=sa.String(500))
    op.alter_column('driver_bank_details', 'upi_id', type_=sa.String(100), existing_type=sa.String(500))
    
    op.alter_column('driver_documents', 'govt_id_number', type_=sa.String(100), existing_type=sa.String(500))
    op.alter_column('driver_documents', 'license_number', type_=sa.String(100), existing_type=sa.String(500))
