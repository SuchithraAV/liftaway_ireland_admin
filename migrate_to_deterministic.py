import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

# Keys from .env
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "4sbYn6Kk4nOigTb50yAOXS_AHmyQ3g-syBrqpqTxqnw")
DETERMINISTIC_KEY = os.getenv("DETERMINISTIC_ENCRYPTION_KEY", "egHu5mmgG2cj4SCI5nrAQgCbc0BrmKSiH26IVkGBA60")

def old_decrypt_nondeterministic(encrypted_base64: str) -> str:
    """Decrypt OLD format: non-deterministic with FIELD_ENCRYPTION_KEY (this is what encrypt_existing_data.py used)"""
    if not encrypted_base64:
        return encrypted_base64
    try:
        # OLD encrypt_phone() used FIELD_ENCRYPTION_KEY (not DETERMINISTIC_KEY!)
        key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
        
        encrypted_data = base64.b64decode(encrypted_base64)
        nonce = encrypted_data[:12]  # Random nonce
        ciphertext = encrypted_data[12:]
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        # Try with raw base64 key (in case key format is different)
        try:
            key = base64.urlsafe_b64decode(FIELD_ENCRYPTION_KEY + '==')
            encrypted_data = base64.b64decode(encrypted_base64)
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except:
            print(f"    Decrypt error: {e}")
            return None

def new_encrypt_deterministic(plaintext: str) -> str:
    """Encrypt NEW format: deterministic with DETERMINISTIC_KEY"""
    if not plaintext:
        return plaintext
    try:
        # New method uses DETERMINISTIC_KEY with fixed nonce
        key = hashlib.sha256(DETERMINISTIC_KEY.encode('utf-8')).digest()
        nonce = hashlib.sha256(plaintext.encode('utf-8')).digest()[:12]  # Fixed nonce from plaintext
        
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        encrypted_data = nonce + ciphertext  # Store nonce with data
        
        return base64.b64encode(encrypted_data).decode('utf-8')
    except Exception as e:
        print(f"    Encrypt error: {e}")
        raise

def new_encrypt_nondeterministic(plaintext: str) -> str:
    """Encrypt NEW format: non-deterministic for non-searchable fields"""
    if not plaintext:
        return plaintext
    try:
        key = hashlib.sha256(FIELD_ENCRYPTION_KEY.encode('utf-8')).digest()
        nonce = os.urandom(12)  # Random nonce
        
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        encrypted_data = nonce + ciphertext
        
        return base64.b64encode(encrypted_data).decode('utf-8')
    except Exception as e:
        print(f"    Encrypt error: {e}")
        raise

async def migrate_encryption():
    async for db in get_db():
        # Migrate Drivers
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        print(f"Found {len(drivers)} drivers to migrate\n")
        
        migrated_count = 0
        for driver in drivers:
            print(f"Driver {driver.id}:")
            try:
                # Decrypt phone (old non-deterministic)
                phone_plain = old_decrypt_nondeterministic(driver.phone_number)
                if not phone_plain:
                    print(f"  ❌ Failed to decrypt phone")
                    continue
                
                print(f"  Phone: {phone_plain}")
                
                # Re-encrypt with new deterministic format
                driver.phone_number = new_encrypt_deterministic(phone_plain)
                
                # Decrypt and re-encrypt email
                if driver.email:
                    email_plain = old_decrypt_nondeterministic(driver.email)
                    if email_plain:
                        driver.email = new_encrypt_deterministic(email_plain)
                        print(f"  Email: {email_plain}")
                
                # Decrypt and re-encrypt name
                if driver.full_name:
                    name_plain = old_decrypt_nondeterministic(driver.full_name)
                    if name_plain:
                        driver.full_name = new_encrypt_deterministic(name_plain)
                        print(f"  Name: {name_plain}")
                
                # Decrypt and re-encrypt address (non-deterministic)
                if driver.address:
                    address_plain = old_decrypt_nondeterministic(driver.address)
                    if address_plain:
                        driver.address = new_encrypt_nondeterministic(address_plain)
                
                # Decrypt and re-encrypt govt_id (non-deterministic)
                if driver.govt_id_number:
                    govt_id_plain = old_decrypt_nondeterministic(driver.govt_id_number)
                    if govt_id_plain:
                        driver.govt_id_number = new_encrypt_nondeterministic(govt_id_plain)
                
                # Decrypt and re-encrypt bank account (non-deterministic)
                if driver.bank_account_number:
                    bank_plain = old_decrypt_nondeterministic(driver.bank_account_number)
                    if bank_plain:
                        driver.bank_account_number = new_encrypt_nondeterministic(bank_plain)
                
                # Decrypt and re-encrypt account holder name (deterministic)
                if driver.account_holder_name:
                    holder_plain = old_decrypt_nondeterministic(driver.account_holder_name)
                    if holder_plain:
                        driver.account_holder_name = new_encrypt_deterministic(holder_plain)
                
                print(f"  ✅ Migrated successfully\n")
                migrated_count += 1
                
            except Exception as e:
                print(f"  ❌ Error: {e}\n")
        
        # Migrate Admins
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        print(f"\nFound {len(admins)} admins to migrate\n")
        
        for admin in admins:
            print(f"Admin {admin.id}:")
            try:
                # Decrypt phone (old non-deterministic)
                phone_plain = old_decrypt_nondeterministic(admin.phone_number)
                if not phone_plain:
                    print(f"  ❌ Failed to decrypt phone")
                    continue
                
                print(f"  Phone: {phone_plain}")
                
                # Re-encrypt with new deterministic format
                admin.phone_number = new_encrypt_deterministic(phone_plain)
                
                print(f"  ✅ Migrated successfully\n")
                migrated_count += 1
                
            except Exception as e:
                print(f"  ❌ Error: {e}\n")
        
        await db.commit()
        print(f"\n{'='*60}")
        print(f"✅ Migration complete! Migrated {migrated_count} records.")
        print(f"{'='*60}")
        break

if __name__ == "__main__":
    asyncio.run(migrate_encryption())
