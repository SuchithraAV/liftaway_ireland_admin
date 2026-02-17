"""
Example: How to add encryption to Driver model

Add this to your core/models.py Driver class:
"""

from sqlalchemy.ext.hybrid import hybrid_property
from core.utils.encryption_service import encrypt_field, decrypt_field, encrypt_deterministic, decrypt_deterministic

# In Driver class, replace existing columns with encrypted versions:

# 1. PHONE NUMBER - Use deterministic encryption (searchable for login)
# Replace: phone_number = Column(String(20), nullable=True)
# With:
phone_number_encrypted = Column(String(500), nullable=True, name="phone_number")

@hybrid_property
def phone_number(self):
    """Decrypt phone number when reading"""
    if self.phone_number_encrypted:
        return decrypt_deterministic(self.phone_number_encrypted)
    return None

@phone_number.setter
def phone_number(self, value):
    """Encrypt phone number when writing"""
    if value:
        self.phone_number_encrypted = encrypt_deterministic(value)
    else:
        self.phone_number_encrypted = None


# 2. FULL NAME - Use random encryption (not searchable)
# Replace: full_name = Column(String(255), nullable=True)
# With:
full_name_encrypted = Column(String(500), nullable=True, name="full_name")

@hybrid_property
def full_name(self):
    """Decrypt name when reading"""
    if self.full_name_encrypted:
        return decrypt_field(self.full_name_encrypted)
    return None

@full_name.setter
def full_name(self, value):
    """Encrypt name when writing"""
    if value:
        self.full_name_encrypted = encrypt_field(value)
    else:
        self.full_name_encrypted = None


# 3. EMAIL - Use random encryption (not searchable)
# Replace: email = Column(String(255), unique=True, nullable=True, index=True)
# With:
email_encrypted = Column(String(500), nullable=True, name="email")

@hybrid_property
def email(self):
    """Decrypt email when reading"""
    if self.email_encrypted:
        return decrypt_field(self.email_encrypted)
    return None

@email.setter
def email(self, value):
    """Encrypt email when writing"""
    if value:
        self.email_encrypted = encrypt_field(value)
    else:
        self.email_encrypted = None


# 4. ADDRESS - Use random encryption
# Replace: address = Column(Text, nullable=True)
# With:
address_encrypted = Column(Text, nullable=True, name="address")

@hybrid_property
def address(self):
    """Decrypt address when reading"""
    if self.address_encrypted:
        return decrypt_field(self.address_encrypted)
    return None

@address.setter
def address(self, value):
    """Encrypt address when writing"""
    if value:
        self.address_encrypted = encrypt_field(value)
    else:
        self.address_encrypted = None


"""
HOW IT WORKS:

1. SAVING DATA:
   driver = Driver()
   driver.phone_number = "+918088101063"  # Automatically encrypted
   driver.full_name = "John Doe"          # Automatically encrypted
   db.add(driver)
   await db.commit()
   # Database stores encrypted values

2. READING DATA:
   driver = await db.get(Driver, driver_id)
   print(driver.phone_number)  # Automatically decrypted: "+918088101063"
   print(driver.full_name)     # Automatically decrypted: "John Doe"

3. SEARCHING (only works for deterministic encryption):
   # This works for phone_number (deterministic):
   encrypted_phone = encrypt_deterministic("+918088101063")
   driver = await db.execute(
       select(Driver).where(Driver.phone_number_encrypted == encrypted_phone)
   )
   
   # This DOESN'T work for full_name (random encryption):
   # Can't search encrypted random fields

MIGRATION NEEDED:
- Rename columns in database: phone_number → phone_number (keep same)
- Increase column sizes to VARCHAR(500) for encrypted data
- Run migration to encrypt existing data
"""
