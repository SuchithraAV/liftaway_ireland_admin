import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

# Old decryption (non-deterministic with random nonce)
def old_decrypt(encrypted_base64: str) -> str:
    if not encrypted_base64:
        return encrypted_base64
    try:
        FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "FieldEncryptionKey2024!@#$%^&*")
        key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
        
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        # If decryption fails, return as-is (might already be plaintext or new format)
        return encrypted_base64

# New encryption (deterministic)
def new_encrypt(plaintext: str, deterministic: bool = True) -> str:
    if not plaintext:
        return plaintext
    try:
        if deterministic:
            DETERMINISTIC_KEY = os.getenv("DETERMINISTIC_ENCRYPTION_KEY", "DeterministicKey2024!@#$%^&*")
            key = hashlib.sha256(DETERMINISTIC_KEY.encode('utf-8')).digest()
            nonce = hashlib.sha256(plaintext.encode('utf-8')).digest()[:12]
        else:
            FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "FieldEncryptionKey2024!@#$%^&*")
            key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
            nonce = os.urandom(12)
        
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        encrypted_data = nonce + ciphertext
        
        return base64.b64encode(encrypted_data).decode('utf-8')
    except Exception as e:
        print(f"Encrypt error: {e}")
        raise

async def migrate_data():
    async for db in get_db():
        # Migrate Drivers
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        print(f"Found {len(drivers)} drivers to migrate")
        
        for driver in drivers:
            try:
                # Decrypt old format
                phone_plain = old_decrypt(driver.phone_number)
                email_plain = old_decrypt(driver.email) if driver.email else ""
                name_plain = old_decrypt(driver.full_name) if driver.full_name else ""
                address_plain = old_decrypt(driver.address) if driver.address else ""
                
                # Re-encrypt with new deterministic format
                driver.phone_number = new_encrypt(phone_plain, deterministic=True)
                driver.email = new_encrypt(email_plain, deterministic=True) if email_plain else ""
                driver.full_name = new_encrypt(name_plain, deterministic=True) if name_plain else ""
                driver.address = new_encrypt(address_plain, deterministic=False) if address_plain else ""
                
                # Encrypt sensitive fields
                if driver.govt_id_number:
                    govt_id_plain = old_decrypt(driver.govt_id_number)
                    driver.govt_id_number = new_encrypt(govt_id_plain, deterministic=False)
                
                if driver.bank_account_number:
                    bank_plain = old_decrypt(driver.bank_account_number)
                    driver.bank_account_number = new_encrypt(bank_plain, deterministic=False)
                
                if driver.account_holder_name:
                    holder_plain = old_decrypt(driver.account_holder_name)
                    driver.account_holder_name = new_encrypt(holder_plain, deterministic=True)
                
                print(f"✅ Migrated driver: {phone_plain}")
                
            except Exception as e:
                print(f"❌ Error migrating driver {driver.id}: {e}")
        
        # Migrate Admins
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        print(f"\nFound {len(admins)} admins to migrate")
        
        for admin in admins:
            try:
                # Decrypt old format
                phone_plain = old_decrypt(admin.phone_number)
                
                # Re-encrypt with new deterministic format
                admin.phone_number = new_encrypt(phone_plain, deterministic=True)
                
                print(f"✅ Migrated admin: {phone_plain}")
                
            except Exception as e:
                print(f"❌ Error migrating admin {admin.id}: {e}")
        
        await db.commit()
        print("\n✅ Migration complete! All data re-encrypted with new format.")
        break

if __name__ == "__main__":
    asyncio.run(migrate_data())
