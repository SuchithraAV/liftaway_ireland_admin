"""
Encrypt Existing Driver & Admin Data
=====================================

This script encrypts plaintext phone numbers, emails, and other PII
for drivers and admins that are currently stored in plaintext.

⚠️ BACKUP YOUR DATABASE BEFORE RUNNING!

Usage:
    python encrypt_driver_admin_data.py
"""

import asyncio
from sqlalchemy import select, update
from core.database import get_db
from core.models import Driver, Admin
from core.utils.field_encryption import (
    encrypt_phone, encrypt_email, encrypt_field, 
    encrypt_address, encrypt_bank_account, encrypt_govt_id,
    is_encrypted
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def encrypt_drivers():
    """Encrypt driver PII data"""
    logger.info("="*60)
    logger.info("🚗 ENCRYPTING DRIVER DATA")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        logger.info(f"Found {len(drivers)} drivers")
        
        encrypted_count = 0
        for driver in drivers:
            try:
                updates = {}
                
                # Phone number
                if driver.phone_number and not is_encrypted(driver.phone_number):
                    logger.info(f"  Encrypting phone: {driver.phone_number}")
                    updates['phone_number'] = encrypt_phone(driver.phone_number)
                
                # Email
                if driver.email and not is_encrypted(driver.email):
                    logger.info(f"  Encrypting email: {driver.email}")
                    updates['email'] = encrypt_email(driver.email)
                
                # Full name
                if driver.full_name and not is_encrypted(driver.full_name):
                    logger.info(f"  Encrypting name: {driver.full_name}")
                    updates['full_name'] = encrypt_field(driver.full_name)
                
                # Address
                if driver.address and not is_encrypted(driver.address):
                    logger.info(f"  Encrypting address")
                    updates['address'] = encrypt_address(driver.address)
                
                if updates:
                    await db.execute(
                        update(Driver)
                        .where(Driver.id == driver.id)
                        .values(**updates)
                    )
                    encrypted_count += 1
                    logger.info(f"  ✅ Driver {driver.id} encrypted")
            
            except Exception as e:
                logger.error(f"  ❌ Failed to encrypt driver {driver.id}: {e}")
        
        await db.commit()
        logger.info(f"\n✅ Encrypted {encrypted_count} drivers")
        break


async def encrypt_admins():
    """Encrypt admin PII data"""
    logger.info("\n" + "="*60)
    logger.info("👔 ENCRYPTING ADMIN DATA")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        logger.info(f"Found {len(admins)} admins")
        
        encrypted_count = 0
        for admin in admins:
            try:
                updates = {}
                
                # Phone number
                if admin.phone_number and not is_encrypted(admin.phone_number):
                    logger.info(f"  Encrypting phone: {admin.phone_number}")
                    updates['phone_number'] = encrypt_phone(admin.phone_number)
                
                if updates:
                    await db.execute(
                        update(Admin)
                        .where(Admin.id == admin.id)
                        .values(**updates)
                    )
                    encrypted_count += 1
                    logger.info(f"  ✅ Admin {admin.id} encrypted")
            
            except Exception as e:
                logger.error(f"  ❌ Failed to encrypt admin {admin.id}: {e}")
        
        await db.commit()
        logger.info(f"\n✅ Encrypted {encrypted_count} admins")
        break


async def main():
    """Run encryption for all user types"""
    logger.info("\n" + "="*60)
    logger.info("🔒 ENCRYPTING EXISTING DRIVER & ADMIN DATA")
    logger.info("="*60)
    logger.info("⚠️  Make sure you have backed up your database!")
    logger.info("="*60)
    
    try:
        await encrypt_drivers()
        await encrypt_admins()
        
        logger.info("\n" + "="*60)
        logger.info("✅ ENCRYPTION COMPLETE!")
        logger.info("="*60)
        logger.info("\nNext steps:")
        logger.info("1. Test driver login")
        logger.info("2. Test admin login")
        logger.info("3. Verify data is encrypted in database")
        logger.info("4. Verify login/registration works correctly")
    
    except Exception as e:
        logger.error(f"\n❌ ENCRYPTION FAILED: {e}")
        logger.error("Database may be in inconsistent state - restore from backup!")
        raise


if __name__ == "__main__":
    asyncio.run(main())
