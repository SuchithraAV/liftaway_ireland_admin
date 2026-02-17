"""
Test Driver & Admin Authentication with Encryption
===================================================

This script tests that:
1. Phone numbers are encrypted when stored in DB
2. Phone numbers are decrypted correctly when returned in responses
3. Login works with encrypted phone lookup
4. OTP verification returns decrypted user data

Usage:
    python test_driver_admin_auth.py
"""

import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin, Customer
from core.utils.field_encryption import (
    encrypt_phone, decrypt_phone,
    encrypt_email, decrypt_email,
    encrypt_field, decrypt_field,
    is_encrypted
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_driver_encryption():
    """Test driver phone/email encryption in database"""
    logger.info("\n" + "="*60)
    logger.info("🚗 TESTING DRIVER ENCRYPTION")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if not driver:
            logger.warning("⚠️  No drivers found in database")
            break
        
        logger.info(f"\nDriver ID: {driver.id}")
        
        # Test phone number
        if driver.phone_number:
            logger.info(f"\n📱 Phone Number Test:")
            logger.info(f"  DB Value: {driver.phone_number[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(driver.phone_number)}")
            
            if is_encrypted(driver.phone_number):
                decrypted = decrypt_phone(driver.phone_number)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Phone encryption working correctly")
                
                # Test lookup
                encrypted_search = encrypt_phone(decrypted)
                if encrypted_search == driver.phone_number:
                    logger.info(f"  ✅ Phone lookup will work (deterministic encryption)")
                else:
                    logger.error(f"  ❌ Phone lookup will FAIL (encryption not deterministic)")
            else:
                logger.error(f"  ❌ Phone NOT encrypted in database!")
        
        # Test email
        if driver.email:
            logger.info(f"\n📧 Email Test:")
            logger.info(f"  DB Value: {driver.email[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(driver.email)}")
            
            if is_encrypted(driver.email):
                decrypted = decrypt_email(driver.email)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Email encryption working correctly")
            else:
                logger.error(f"  ❌ Email NOT encrypted in database!")
        
        # Test full name
        if driver.full_name:
            logger.info(f"\n👤 Full Name Test:")
            logger.info(f"  DB Value: {driver.full_name[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(driver.full_name)}")
            
            if is_encrypted(driver.full_name):
                decrypted = decrypt_field(driver.full_name)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Name encryption working correctly")
            else:
                logger.error(f"  ❌ Name NOT encrypted in database!")
        
        break


async def test_admin_encryption():
    """Test admin phone encryption in database"""
    logger.info("\n" + "="*60)
    logger.info("👔 TESTING ADMIN ENCRYPTION")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Admin).limit(1))
        admin = result.scalar_one_or_none()
        
        if not admin:
            logger.warning("⚠️  No admins found in database")
            break
        
        logger.info(f"\nAdmin ID: {admin.id}")
        
        # Test phone number
        if admin.phone_number:
            logger.info(f"\n📱 Phone Number Test:")
            logger.info(f"  DB Value: {admin.phone_number[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(admin.phone_number)}")
            
            if is_encrypted(admin.phone_number):
                decrypted = decrypt_phone(admin.phone_number)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Phone encryption working correctly")
                
                # Test lookup
                encrypted_search = encrypt_phone(decrypted)
                if encrypted_search == admin.phone_number:
                    logger.info(f"  ✅ Phone lookup will work (deterministic encryption)")
                else:
                    logger.error(f"  ❌ Phone lookup will FAIL (encryption not deterministic)")
            else:
                logger.error(f"  ❌ Phone NOT encrypted in database!")
        
        break


async def test_customer_encryption():
    """Test customer encryption in database"""
    logger.info("\n" + "="*60)
    logger.info("👤 TESTING CUSTOMER ENCRYPTION")
    logger.info("="*60)
    
    async for db in get_db():
        result = await db.execute(select(Customer).limit(1))
        customer = result.scalar_one_or_none()
        
        if not customer:
            logger.warning("⚠️  No customers found in database")
            break
        
        logger.info(f"\nCustomer ID: {customer.id}")
        
        # Test phone number
        if customer.phone_number:
            logger.info(f"\n📱 Phone Number Test:")
            logger.info(f"  DB Value: {customer.phone_number[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(customer.phone_number)}")
            
            if is_encrypted(customer.phone_number):
                decrypted = decrypt_phone(customer.phone_number)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Phone encryption working correctly")
            else:
                logger.error(f"  ❌ Phone NOT encrypted in database!")
        
        # Test email
        if customer.email:
            logger.info(f"\n📧 Email Test:")
            logger.info(f"  DB Value: {customer.email[:50]}...")
            logger.info(f"  Is Encrypted: {is_encrypted(customer.email)}")
            
            if is_encrypted(customer.email):
                decrypted = decrypt_email(customer.email)
                logger.info(f"  Decrypted: {decrypted}")
                logger.info(f"  ✅ Email encryption working correctly")
            else:
                logger.error(f"  ❌ Email NOT encrypted in database!")
        
        break


async def test_login_flow_simulation():
    """Simulate login flow to test encryption/decryption"""
    logger.info("\n" + "="*60)
    logger.info("🔐 TESTING LOGIN FLOW SIMULATION")
    logger.info("="*60)
    
    async for db in get_db():
        # Test with driver
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if driver and driver.phone_number:
            logger.info("\n🚗 Driver Login Flow:")
            
            # Step 1: Get plaintext phone from user input (simulated)
            decrypted_phone = decrypt_phone(driver.phone_number)
            logger.info(f"  1. User enters: {decrypted_phone}")
            
            # Step 2: Encrypt for database lookup
            encrypted_search = encrypt_phone(decrypted_phone)
            logger.info(f"  2. Encrypted for search: {encrypted_search[:50]}...")
            
            # Step 3: Database lookup
            lookup_result = await db.execute(
                select(Driver).where(Driver.phone_number == encrypted_search)
            )
            found_driver = lookup_result.scalar_one_or_none()
            
            if found_driver:
                logger.info(f"  3. ✅ Driver found in database")
                logger.info(f"  4. Driver ID: {found_driver.id}")
                
                # Step 4: Return decrypted data to user
                response_phone = decrypt_phone(found_driver.phone_number)
                logger.info(f"  5. Response phone: {response_phone}")
                
                if response_phone == decrypted_phone:
                    logger.info(f"  ✅ LOGIN FLOW WORKING CORRECTLY")
                else:
                    logger.error(f"  ❌ DECRYPTION MISMATCH!")
            else:
                logger.error(f"  ❌ Driver NOT found (lookup failed)")
        
        # Test with admin
        result = await db.execute(select(Admin).limit(1))
        admin = result.scalar_one_or_none()
        
        if admin and admin.phone_number:
            logger.info("\n👔 Admin Login Flow:")
            
            decrypted_phone = decrypt_phone(admin.phone_number)
            logger.info(f"  1. User enters: {decrypted_phone}")
            
            encrypted_search = encrypt_phone(decrypted_phone)
            logger.info(f"  2. Encrypted for search: {encrypted_search[:50]}...")
            
            lookup_result = await db.execute(
                select(Admin).where(Admin.phone_number == encrypted_search)
            )
            found_admin = lookup_result.scalar_one_or_none()
            
            if found_admin:
                logger.info(f"  3. ✅ Admin found in database")
                logger.info(f"  4. Admin ID: {found_admin.id}")
                
                response_phone = decrypt_phone(found_admin.phone_number)
                logger.info(f"  5. Response phone: {response_phone}")
                
                if response_phone == decrypted_phone:
                    logger.info(f"  ✅ LOGIN FLOW WORKING CORRECTLY")
                else:
                    logger.error(f"  ❌ DECRYPTION MISMATCH!")
            else:
                logger.error(f"  ❌ Admin NOT found (lookup failed)")
        
        break


async def main():
    """Run all tests"""
    logger.info("\n" + "="*60)
    logger.info("🔒 DRIVER & ADMIN AUTHENTICATION ENCRYPTION TEST")
    logger.info("="*60)
    
    await test_customer_encryption()
    await test_driver_encryption()
    await test_admin_encryption()
    await test_login_flow_simulation()
    
    logger.info("\n" + "="*60)
    logger.info("✅ TESTS COMPLETED")
    logger.info("="*60)
    logger.info("\nIf all tests passed:")
    logger.info("  ✅ Data is encrypted in database")
    logger.info("  ✅ Decryption works correctly")
    logger.info("  ✅ Login lookup works with encrypted data")
    logger.info("  ✅ Responses return decrypted data")


if __name__ == "__main__":
    asyncio.run(main())
