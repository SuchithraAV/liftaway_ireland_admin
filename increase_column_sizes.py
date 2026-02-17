"""
Run SQL to increase column sizes for encryption

This bypasses Alembic and runs SQL directly on the database.
"""

import asyncio
from core.database import AsyncSessionLocal
from sqlalchemy import text

async def increase_column_sizes():
    print("Increasing column sizes for encryption...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Customers table
            await db.execute(text("ALTER TABLE customers ALTER COLUMN phone_number TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE customers ALTER COLUMN email TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE customers ALTER COLUMN full_name TYPE VARCHAR(500)"))
            print("✅ Updated customers table")
            
            # Drivers table
            await db.execute(text("ALTER TABLE drivers ALTER COLUMN phone_number TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE drivers ALTER COLUMN email TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE drivers ALTER COLUMN full_name TYPE VARCHAR(500)"))
            print("✅ Updated drivers table")
            
            # Admins table
            await db.execute(text("ALTER TABLE admins ALTER COLUMN phone_number TYPE VARCHAR(500)"))
            print("✅ Updated admins table")
            
            # Driver bank details
            await db.execute(text("ALTER TABLE driver_bank_details ALTER COLUMN bank_account_number TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE driver_bank_details ALTER COLUMN bank_ifsc TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE driver_bank_details ALTER COLUMN account_holder_name TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE driver_bank_details ALTER COLUMN upi_id TYPE VARCHAR(500)"))
            print("✅ Updated driver_bank_details table")
            
            # Driver documents
            await db.execute(text("ALTER TABLE driver_documents ALTER COLUMN govt_id_number TYPE VARCHAR(500)"))
            await db.execute(text("ALTER TABLE driver_documents ALTER COLUMN license_number TYPE VARCHAR(500)"))
            print("✅ Updated driver_documents table")
            
            await db.commit()
            print("\n" + "="*60)
            print("✅ All column sizes increased successfully!")
            print("="*60)
            print("\nNow run: python encrypt_existing_data.py")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(increase_column_sizes())
