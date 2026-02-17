"""
Production-ready encryption using AWS KMS with envelope encryption
- Uses KMS to encrypt/decrypt a data encryption key (DEK)
- Uses DEK locally for fast field encryption
- Supports both random and deterministic encryption
"""
import boto3
import base64
import os
from cryptography.fernet import Fernet
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Configuration
USE_KMS = os.getenv("USE_KMS", "false").lower() == "true"
KMS_KEY_ID = os.getenv("KMS_KEY_ID")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Local keys for development
LOCAL_FIELD_KEY = os.getenv("FIELD_ENCRYPTION_KEY")
LOCAL_DETERMINISTIC_KEY = os.getenv("DETERMINISTIC_ENCRYPTION_KEY")


class EncryptionService:
    """
    Encryption service with KMS envelope encryption
    - In development: Uses local Fernet keys
    - In production: Uses KMS to protect data encryption keys
    """
    
    def __init__(self):
        self._field_cipher = None
        self._deterministic_cipher = None
        
        if USE_KMS:
            if not KMS_KEY_ID:
                raise ValueError("KMS_KEY_ID must be set when USE_KMS=true")
            self.kms_client = boto3.client('kms', region_name=AWS_REGION)
            self._init_kms_keys()
            logger.info(f"✅ KMS encryption enabled (Key: {KMS_KEY_ID})")
        else:
            self._init_local_keys()
            logger.info("⚠️ Using local encryption keys (development mode)")
    
    def _init_local_keys(self):
        """Initialize with local Fernet keys for development"""
        if not LOCAL_FIELD_KEY or not LOCAL_DETERMINISTIC_KEY:
            raise ValueError("FIELD_ENCRYPTION_KEY and DETERMINISTIC_ENCRYPTION_KEY must be set")
        
        self._field_cipher = Fernet(LOCAL_FIELD_KEY.encode())
        self._deterministic_cipher = Fernet(LOCAL_DETERMINISTIC_KEY.encode())
    
    def _init_kms_keys(self):
        """
        Initialize encryption keys using KMS envelope encryption
        - For production: Store encrypted data keys in environment/secrets
        - Decrypt them with KMS on startup
        - Use plaintext keys for encryption (cached in memory)
        """
        try:
            # Check if we have pre-generated encrypted data keys
            encrypted_field_key = os.getenv("KMS_ENCRYPTED_FIELD_KEY")
            encrypted_det_key = os.getenv("KMS_ENCRYPTED_DET_KEY")
            
            if encrypted_field_key and encrypted_det_key:
                # Decrypt existing data keys (production mode)
                logger.info("Decrypting existing data keys with KMS...")
                
                field_response = self.kms_client.decrypt(
                    CiphertextBlob=base64.b64decode(encrypted_field_key)
                )
                det_response = self.kms_client.decrypt(
                    CiphertextBlob=base64.b64decode(encrypted_det_key)
                )
                
                field_key = base64.urlsafe_b64encode(field_response['Plaintext'][:32])
                det_key = base64.urlsafe_b64encode(det_response['Plaintext'][:32])
                
                self._field_cipher = Fernet(field_key)
                self._deterministic_cipher = Fernet(det_key)
                
                logger.info("✅ Existing KMS data keys decrypted and loaded")
            else:
                # Generate new data keys (first-time setup)
                logger.warning("⚠️ Generating NEW data keys - save these for production!")
                
                # Generate field encryption key
                field_response = self.kms_client.generate_data_key(
                    KeyId=KMS_KEY_ID,
                    KeySpec='AES_256'
                )
                
                # Generate deterministic encryption key
                det_response = self.kms_client.generate_data_key(
                    KeyId=KMS_KEY_ID,
                    KeySpec='AES_256'
                )
                
                # Use plaintext keys for encryption
                field_key = base64.urlsafe_b64encode(field_response['Plaintext'][:32])
                det_key = base64.urlsafe_b64encode(det_response['Plaintext'][:32])
                
                self._field_cipher = Fernet(field_key)
                self._deterministic_cipher = Fernet(det_key)
                
                # Print encrypted keys to save in environment variables
                encrypted_field = base64.b64encode(field_response['CiphertextBlob']).decode()
                encrypted_det = base64.b64encode(det_response['CiphertextBlob']).decode()
                
                logger.warning("="*80)
                logger.warning("SAVE THESE ENCRYPTED KEYS IN YOUR PRODUCTION ENVIRONMENT:")
                logger.warning(f"KMS_ENCRYPTED_FIELD_KEY={encrypted_field}")
                logger.warning(f"KMS_ENCRYPTED_DET_KEY={encrypted_det}")
                logger.warning("="*80)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize KMS keys: {e}")
            raise
    
    def encrypt_field(self, plaintext: Optional[str]) -> Optional[str]:
        """
        Encrypt sensitive field (random encryption)
        Use for: name, email, address, etc.
        """
        if not plaintext:
            return plaintext
        
        try:
            encrypted = self._field_cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Field encryption error: {e}")
            raise
    
    def decrypt_field(self, ciphertext: Optional[str]) -> Optional[str]:
        """
        Decrypt sensitive field
        """
        if not ciphertext:
            return ciphertext
        
        try:
            decrypted = self._field_cipher.decrypt(ciphertext.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Field decryption error: {e}")
            raise
    
    def encrypt_deterministic(self, plaintext: Optional[str]) -> Optional[str]:
        """
        Deterministic encryption for searchable fields
        Use for: phone numbers (for login lookup)
        Same input always produces same output
        """
        if not plaintext:
            return plaintext
        
        try:
            encrypted = self._deterministic_cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Deterministic encryption error: {e}")
            raise
    
    def decrypt_deterministic(self, ciphertext: Optional[str]) -> Optional[str]:
        """
        Decrypt deterministic encrypted data
        """
        if not ciphertext:
            return ciphertext
        
        try:
            decrypted = self._deterministic_cipher.decrypt(ciphertext.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Deterministic decryption error: {e}")
            raise


# Global singleton instance
_encryption_service = None


def get_encryption_service() -> EncryptionService:
    """Get or create encryption service singleton"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


# Convenience functions for backward compatibility
def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt sensitive field"""
    return get_encryption_service().encrypt_field(plaintext)


def decrypt_field(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt sensitive field"""
    return get_encryption_service().decrypt_field(ciphertext)


def encrypt_deterministic(plaintext: Optional[str]) -> Optional[str]:
    """Deterministic encryption for searchable fields"""
    return get_encryption_service().encrypt_deterministic(plaintext)


def decrypt_deterministic(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt deterministic encrypted data"""
    return get_encryption_service().decrypt_deterministic(ciphertext)


# Example usage in models:
"""
from core.utils.encryption_service import encrypt_field, decrypt_field, encrypt_deterministic

class Driver(Base):
    # Searchable field - use deterministic encryption
    phone_number_encrypted = Column(String(500))
    
    @property
    def phone_number(self):
        return decrypt_deterministic(self.phone_number_encrypted)
    
    @phone_number.setter
    def phone_number(self, value):
        self.phone_number_encrypted = encrypt_deterministic(value)
    
    # Non-searchable sensitive field - use random encryption
    full_name_encrypted = Column(String(500))
    
    @property
    def full_name(self):
        return decrypt_field(self.full_name_encrypted)
    
    @full_name.setter
    def full_name(self, value):
        self.full_name_encrypted = encrypt_field(value)
"""
