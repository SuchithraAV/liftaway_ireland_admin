import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver
from core.utils.field_encryption import encrypt_phone

async def check_driver_data():
    test_phone = "+919642777143"  # From earlier output
    
    async for db in get_db():
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if driver:
            print(f"Driver phone in DB: {driver.phone_number}")
            print(f"Is it plaintext? {driver.phone_number.startswith('+')}")
            print(f"Is it encrypted? {len(driver.phone_number) > 40}")
            
            # Try encrypting the test phone
            encrypted = encrypt_phone(test_phone)
            print(f"\nEncrypted test phone: {encrypted[:50]}...")
            
            # Check if they match
            if driver.phone_number == encrypted:
                print("✅ DB has encrypted data - encryption is working")
            elif driver.phone_number == test_phone:
                print("❌ DB has PLAINTEXT - need to run encrypt_existing_data.py")
            else:
                print("⚠️ DB has different encrypted format")
        else:
            print("No drivers found")
        break

if __name__ == "__main__":
    asyncio.run(check_driver_data())
