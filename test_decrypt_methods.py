import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Actual keys from .env
FIELD_ENCRYPTION_KEY = "4sbYn6Kk4nOigTb50yAOXS_AHmyQ3g-syBrqpqTxqnw"
DETERMINISTIC_KEY = "egHu5mmgG2cj4SCI5nrAQgCbc0BrmKSiH26IVkGBA60"

def try_decrypt_method1(encrypted_base64: str) -> str:
    """Try non-deterministic with FIELD_ENCRYPTION_KEY"""
    try:
        key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        return None

def try_decrypt_method2(encrypted_base64: str) -> str:
    """Try deterministic with DETERMINISTIC_KEY"""
    try:
        key = hashlib.sha256(DETERMINISTIC_KEY.encode('utf-8')).digest()
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        return None

def try_decrypt_method3(encrypted_base64: str) -> str:
    """Try using raw key (base64 decoded)"""
    try:
        key = base64.urlsafe_b64decode(FIELD_ENCRYPTION_KEY + '==')
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        return None

async def test_all_methods():
    async for db in get_db():
        # Test Driver
        result = await db.execute(select(Driver).limit(1))
        driver = result.scalar_one_or_none()
        
        if driver:
            print("=" * 60)
            print("TESTING DRIVER DECRYPTION")
            print("=" * 60)
            print(f"Encrypted phone: {driver.phone_number[:50]}...")
            
            result = try_decrypt_method1(driver.phone_number)
            if result:
                print(f"✅ Method 1 (FIELD_ENCRYPTION_KEY + SHA256): {result}")
            else:
                print(f"❌ Method 1 failed")
            
            result = try_decrypt_method2(driver.phone_number)
            if result:
                print(f"✅ Method 2 (DETERMINISTIC_KEY + SHA256): {result}")
            else:
                print(f"❌ Method 2 failed")
            
            result = try_decrypt_method3(driver.phone_number)
            if result:
                print(f"✅ Method 3 (Raw base64 key): {result}")
            else:
                print(f"❌ Method 3 failed")
        
        # Test Admin
        result = await db.execute(select(Admin).limit(1))
        admin = result.scalar_one_or_none()
        
        if admin:
            print("\n" + "=" * 60)
            print("TESTING ADMIN DECRYPTION")
            print("=" * 60)
            print(f"Encrypted phone: {admin.phone_number[:50]}...")
            
            result = try_decrypt_method1(admin.phone_number)
            if result:
                print(f"✅ Method 1 (FIELD_ENCRYPTION_KEY + SHA256): {result}")
            else:
                print(f"❌ Method 1 failed")
            
            result = try_decrypt_method2(admin.phone_number)
            if result:
                print(f"✅ Method 2 (DETERMINISTIC_KEY + SHA256): {result}")
            else:
                print(f"❌ Method 2 failed")
            
            result = try_decrypt_method3(admin.phone_number)
            if result:
                print(f"✅ Method 3 (Raw base64 key): {result}")
            else:
                print(f"❌ Method 3 failed")
        
        break

if __name__ == "__main__":
    asyncio.run(test_all_methods())
