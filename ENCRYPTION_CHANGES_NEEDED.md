## ENCRYPTION STATUS - auth_api.py

### ❌ CURRENTLY NOT ENCRYPTED (Lines 194-245)

```python
# Line 1: Add import at top
from core.utils.field_encryption import encrypt_phone, encrypt_email, encrypt_field, encrypt_bank_account, encrypt_govt_id

# Lines 194-208: Driver creation - NEEDS ENCRYPTION
driver = Driver(
    id=driver_id,
    full_name=encrypt_field(full_name),  # ← ADD encrypt_field()
    phone_number=encrypt_phone(phone_number),  # ← ADD encrypt_phone()
    email=encrypt_email(email),  # ← ADD encrypt_email()
    dob=dob_date,  # Keep as-is (date object)
    address=encrypt_field(address) if address else None,  # ← ADD encrypt_field()
    password=get_password_hash("temp_password"),
    years_experience=years_of_experience,
    service_pincodes=pincodes,
    preferred_shift=preferred_shift,
    phone_otp=otp,
    otp_expires_at=expiry,
    is_verified="pending"
)

# Lines 215-226: DriverDocument - NEEDS ENCRYPTION
doc = DriverDocument(
    driver_id=driver.id,
    govt_id_type=govt_id_type,
    govt_id_number=encrypt_govt_id(govt_id_number) if govt_id_number else None,  # ← ADD
    id_photo_url=get_full_url(govt_id_photo_path) if govt_id_photo_path else None,
    selfie_photo_url=get_full_url(selfie_photo_path) if selfie_photo_path else None,
    license_number=encrypt_field(license_number) if license_number else None,  # ← ADD
    license_category=license_category,
    license_expiry_date=license_expiry_date_obj,
    license_front_url=get_full_url(license_front_path) if license_front_path else None,
    license_back_url=get_full_url(license_back_path) if license_back_path else None,
    driver_photo_url=get_full_url(driver_photo_path) if driver_photo_path else None
)

# Lines 229-234: DriverBankDetail - NEEDS ENCRYPTION
bank = DriverBankDetail(
    driver_id=driver.id,
    bank_account_number=encrypt_bank_account(account_number) if account_number else None,  # ← ADD
    bank_ifsc=encrypt_field(sort_code) if sort_code else None,  # ← ADD
    account_holder_name=encrypt_field(holder_name) if holder_name else None,  # ← ADD
    upi_id=encrypt_field(upi_id) if upi_id else None  # ← ADD
)

# Lines 237-245: DriverVehicle - NEEDS ENCRYPTION
vehicle = DriverVehicle(
    driver_id=driver.id,
    vehicle_type=vehicle_type,
    vehicle_number_plate=encrypt_field(vehicle_number) if vehicle_number else None,  # ← ADD
    vehicle_model=vehicle_model,
    vehicle_capacity=vehicle_capacity,
    vehicle_photo_url=get_full_url(vehicle_photo_path) if vehicle_photo_path else None,
    rc_book_pic_url=get_full_url(rc_book_photo_path) if rc_book_photo_path else None,
    pollution_cert_pic_url=get_full_url(pollution_cert_path) if pollution_cert_path else None
)
```

### ⚠️ ALSO NEED TO FIX: Phone number lookup (Line 155)

```python
# BEFORE (won't work with encrypted phone):
result = await db.execute(select(Driver).where(Driver.phone_number == phone_number))

# AFTER (encrypt phone for lookup):
encrypted_phone = encrypt_phone(phone_number)
result = await db.execute(select(Driver).where(Driver.phone_number == encrypted_phone))
```

### ⚠️ ALSO NEED TO FIX: Email lookup (Line 161)

```python
# BEFORE:
result = await db.execute(select(Driver).where(Driver.email == email))

# AFTER:
encrypted_email = encrypt_email(email)
result = await db.execute(select(Driver).where(Driver.email == encrypted_email))
```

### ✅ SAME CHANGES NEEDED IN:
- Line 357-408: Second registration endpoint
- Line 493-498: Admin registration
- All login/verification endpoints that lookup by phone

### 📝 SUMMARY:
- Add 1 import line
- Encrypt 15 fields before saving
- Encrypt phone/email before database lookups
- Total: ~20 lines to change in auth_api.py
