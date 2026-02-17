"""
Decrypt All Database Data
==========================

⚠️ WARNING: This will convert encrypted data back to plaintext!
This is NOT recommended for production. Only use for:
- Development/testing
- Data migration
- Emergency recovery

⚠️ BACKUP YOUR DATABASE BEFORE RUNNING!

Usage:
    python decrypt_all_database_data.py
"""

import asyncio
from sqlalchemy import select, update
from core.database import get_db
from core.models import Driver, Admin, Customer
from core.utils.field_encryption import (
    decrypt_phone, decrypt_email, decrypt_field, 
    decrypt_address, is_encrypted
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def decrypt_customers():
    """Decrypt customer data"""
    logger.info("="*60)
    logger.info("👤 DECRYPTING CUSTOMER DATA")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Customer))
        customers = result.scalars().all()
        
        logger.info(f"Found {len(customers)} customers")
        
        decrypted_count = 0
        for customer in customers:
            try:
                updates = {}
                
                if customer.phone_number and is_encrypted(customer.phone_number):
                    decrypted = decrypt_phone(customer.phone_number)
                    logger.info(f"  Decrypting phone: {customer.phone_number[:30]}... → {decrypted}")
                    updates['phone_number'] = decrypted
                
                if customer.email and is_encrypted(customer.email):
                    decrypted = decrypt_email(customer.email)
                    logger.info(f"  Decrypting email: {customer.email[:30]}... → {decrypted}")
                    updates['email'] = decrypted
                
                if customer.full_name and is_encrypted(customer.full_name):
                    decrypted = decrypt_field(customer.full_name)
                    logger.info(f"  Decrypting name: {customer.full_name[:30]}... → {decrypted}")
                    updates['full_name'] = decrypted
                
                if customer.address and is_encrypted(customer.address):
                    decrypted = decrypt_address(customer.address)
                    logger.info(f"  Decrypting address")
                    updates['address'] = decrypted
                
                if updates:
                    await db.execute(
                        update(Customer)
                        .where(Customer.id == customer.id)
                        .values(**updates)
                    )
                    decrypted_count += 1
                    logger.info(f"  ✅ Customer {customer.id} decrypted")
            
            except Exception as e:
                logger.error(f"  ❌ Failed to decrypt customer {customer.id}: {e}")
        
        await db.commit()
        logger.info(f"\n✅ Decrypted {decrypted_count} customers")
        break


async def decrypt_drivers():
    """Decrypt driver data"""
    logger.info("\n" + "="*60)
    logger.info("🚗 DECRYPTING DRIVER DATA")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        logger.info(f"Found {len(drivers)} drivers")
        
        decrypted_count = 0
        for driver in drivers:
            try:
                updates = {}
                
                if driver.phone_number and is_encrypted(driver.phone_number):
                    decrypted = decrypt_phone(driver.phone_number)
                    logger.info(f"  Decrypting phone: {driver.phone_number[:30]}... → {decrypted}")
                    updates['phone_number'] = decrypted
                
                if driver.email and is_encrypted(driver.email):
                    decrypted = decrypt_email(driver.email)
                    logger.info(f"  Decrypting email: {driver.email[:30]}... → {decrypted}")
                    updates['email'] = decrypted
                
                if driver.full_name and is_encrypted(driver.full_name):
                    decrypted = decrypt_field(driver.full_name)
                    logger.info(f"  Decrypting name: {driver.full_name[:30]}... → {decrypted}")
                    updates['full_name'] = decrypted
                
                if driver.address and is_encrypted(driver.address):
                    decrypted = decrypt_address(driver.address)
                    logger.info(f"  Decrypting address")
                    updates['address'] = decrypted
                
                if updates:
                    await db.execute(
                        update(Driver)
                        .where(Driver.id == driver.id)
                        .values(**updates)
                    )
                    decrypted_count += 1
                    logger.info(f"  ✅ Driver {driver.id} decrypted")
            
            except Exception as e:
                logger.error(f"  ❌ Failed to decrypt driver {driver.id}: {e}")
        
        await db.commit()
        logger.info(f"\n✅ Decrypted {decrypted_count} drivers")
        break


async def decrypt_admins():
    """Decrypt admin data"""
    logger.info("\n" + "="*60)
    logger.info("👔 DECRYPTING ADMIN DATA")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        logger.info(f"Found {len(admins)} admins")
        
        decrypted_count = 0
        for admin in admins:
            try:
                updates = {}
                
                if admin.phone_number and is_encrypted(admin.phone_number):
                    decrypted = decrypt_phone(admin.phone_number)
                    logger.info(f"  Decrypting phone: {admin.phone_number[:30]}... → {decrypted}")
                    updates['phone_number'] = decrypted
                
                if updates:
                    await db.execute(
                        update(Admin)
                        .where(Admin.id == admin.id)
                        .values(**updates)
                    )
                    decrypted_count += 1
                    logger.info(f"  ✅ Admin {admin.id} decrypted")
            
            except Exception as e:
                logger.error(f"  ❌ Failed to decrypt admin {admin.id}: {e}")
        
        await db.commit()
        logger.info(f"\n✅ Decrypted {decrypted_count} admins")
        break


async def main():
    """Run decryption for all tables"""
    logger.info("\n" + "="*60)
    logger.info("🔓 DECRYPTING ALL DATABASE DATA")
    logger.info("="*60)
    logger.info("⚠️  WARNING: This will convert encrypted data to plaintext!")
    logger.info("⚠️  Make sure you have backed up your database!")
    logger.info("="*60)
    
    try:
        await decrypt_customers()
        await decrypt_drivers()
        await decrypt_admins()
        
        logger.info("\n" + "="*60)
        logger.info("✅ DECRYPTION COMPLETE!")
        logger.info("="*60)
        logger.info("\n⚠️  IMPORTANT:")
        logger.info("1. All PII data is now PLAINTEXT in database")
        logger.info("2. This is NOT secure for production")
        logger.info("3. Login will now search for plaintext values")
        logger.info("4. New registrations will store plaintext (if code not updated)")
    
    except Exception as e:
        logger.error(f"\n❌ DECRYPTION FAILED: {e}")
        logger.error("Database may be in inconsistent state - restore from backup!")
        raise


if __name__ == "__main__":
    asyncio.run(main())
