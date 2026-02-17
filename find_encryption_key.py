import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Try different possible keys
POSSIBLE_KEYS = [
    "4sbYn6Kk4nOigTb50yAOXS_AHmyQ3g-syBrqpqTxqnw",  # Current FIELD_ENCRYPTION_KEY
    "egHu5mmgG2cj4SCI5nrAQgCbc0BrmKSiH26IVkGBA60",  # Current DETERMINISTIC_KEY
    "FieldEncryptionKey2024!@#$%^&*",  # Default from code
    "DeterministicKey2024!@#$%^&*",  # Default from code
    # Add any other keys you might have used
]

def try_decrypt(encrypted_base64: str, key_string: str) -> tuple:
    """Try to decrypt with a given key"""
    try:
        # Method 1: SHA256 hash of key
        key = hashlib.sha256(key_string.encode('utf-8')).digest()
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return (True, plaintext.decode('utf-8'), "SHA256")
    except:
        pass
    
    try:
        # Method 2: Raw base64 key
        key = base64.urlsafe_b64decode(key_string + '==')
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return (True, plaintext.decode('utf-8'), "Base64")
    except:
        pass
    
    return (False, None, None)

async def brute_force_decrypt():
    async for db in get_db():
        # Try one driver
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if driver:
            print("=" * 60)
            print("TRYING TO DECRYPT DRIVER")
            print("=" * 60)
            print(f"Encrypted: {driver.phone_number[:50]}...\n")
            
            for i, key in enumerate(POSSIBLE_KEYS, 1):
                success, plaintext, method = try_decrypt(driver.phone_number, key)
                if success:
                    print(f"✅ SUCCESS with key #{i} ({method}):")
                    print(f"   Key: {key}")
                    print(f"   Decrypted: {plaintext}")
                    print(f"\n🎉 FOUND THE CORRECT KEY! Update your .env:")
                    print(f"   FIELD_ENCRYPTION_KEY={key}")
                    return
                else:
                    print(f"❌ Key #{i} failed: {key[:30]}...")
            
            print("\n❌ None of the keys worked. The data was encrypted with a different key.")
            print("\nOptions:")
            print("1. Find the old encryption key from backups/git history")
            print("2. Truncate and start fresh: python truncate_drivers_admins.py")
        
        break

if __name__ == "__main__":
    print("Attempting to find the correct encryption key...\n")
    asyncio.run(brute_force_decrypt())
