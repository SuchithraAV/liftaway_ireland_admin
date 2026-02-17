import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FIELD_ENCRYPTION_KEY = "DeterministicKey2024!@#$%^&*"

def decrypt_data(encrypted_base64: str) -> str:
    """Decrypt data"""
    if not encrypted_base64:
        return ""
    try:
        key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        return encrypted_base64  # Return as-is if can't decrypt

async def decrypt_database():
    async for db in get_db():
        # Decrypt Drivers
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        print(f"Decrypting {len(drivers)} drivers...")
        
        for driver in drivers:
            driver.phone_number = decrypt_data(driver.phone_number)
            if driver.email:
                driver.email = decrypt_data(driver.email)
            if driver.full_name:
                driver.full_name = decrypt_data(driver.full_name)
            if driver.address:
                driver.address = decrypt_data(driver.address)
            print(f"✅ Decrypted driver: {driver.phone_number}")
        
        # Decrypt Admins
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        print(f"\nDecrypting {len(admins)} admins...")
        
        for admin in admins:
            admin.phone_number = decrypt_data(admin.phone_number)
            print(f"✅ Decrypted admin: {admin.phone_number}")
        
        await db.commit()
        print("\n✅ Database decrypted! All data is now in plaintext.")
        break

if __name__ == "__main__":
    print("⚠️  This will decrypt all data to PLAINTEXT in the database!")
    print("Press Ctrl+C to cancel, or wait 3 seconds...")
    import time
    time.sleep(3)
    asyncio.run(decrypt_database())
