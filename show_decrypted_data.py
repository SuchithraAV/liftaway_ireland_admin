import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The correct key we found
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
        return f"[DECRYPT ERROR: {e}]"

async def show_decrypted_data():
    async for db in get_db():
        # Show Drivers
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        print("=" * 80)
        print(f"DRIVERS ({len(drivers)} total)")
        print("=" * 80)
        
        for driver in drivers:
            print(f"\nDriver ID: {driver.id}")
            print(f"  Phone: {decrypt_data(driver.phone_number)}")
            print(f"  Email: {decrypt_data(driver.email) if driver.email else 'N/A'}")
            print(f"  Name: {decrypt_data(driver.full_name) if driver.full_name else 'N/A'}")
            print(f"  Address: {decrypt_data(driver.address) if driver.address else 'N/A'}")
        
        # Show Admins
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        print("\n" + "=" * 80)
        print(f"ADMINS ({len(admins)} total)")
        print("=" * 80)
        
        for admin in admins:
            print(f"\nAdmin ID: {admin.id}")
            print(f"  Phone: {decrypt_data(admin.phone_number)}")
        
        print("\n" + "=" * 80)
        break

if __name__ == "__main__":
    asyncio.run(show_decrypted_data())
