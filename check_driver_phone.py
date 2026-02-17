import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver
from core.utils.field_encryption import decrypt_phone, encrypt_phone, is_encrypted

async def check_driver_phone():
    async for db in get_db():
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if driver:
            print(f"Driver ID: {driver.id}")
            print(f"Phone in DB: {driver.phone_number}")
            print(f"Is encrypted: {is_encrypted(driver.phone_number)}")
            
            if is_encrypted(driver.phone_number):
                decrypted = decrypt_phone(driver.phone_number)
                print(f"Decrypted: {decrypted}")
                
                # Test if lookup will work
                re_encrypted = encrypt_phone(decrypted)
                print(f"Re-encrypted matches: {re_encrypted == driver.phone_number}")
            else:
                print("⚠️ PHONE NOT ENCRYPTED - PLAINTEXT IN DATABASE!")
                print(f"Plaintext value: {driver.phone_number}")
        else:
            print("No drivers found")
        break

asyncio.run(check_driver_phone())
