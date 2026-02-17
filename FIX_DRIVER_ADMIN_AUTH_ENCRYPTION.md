# 🔧 FIX: Driver & Admin Authentication Encryption Issues

## 🐛 PROBLEM IDENTIFIED

The driver and admin authentication endpoints are **returning encrypted phone numbers** in responses instead of decrypting them. This causes login/registration to fail because:

1. Phone numbers are encrypted when stored in DB
2. Phone numbers are NOT decrypted when returned in responses
3. Frontend receives encrypted gibberish instead of actual phone number

## 📍 AFFECTED FILES

1. `core/routers/auth.py` - Lines where phone_number is returned
2. `core/routers/driver_registration.py` - Registration response

## 🔍 SPECIFIC ISSUES

### Issue 1: Driver Registration Response (Line 348)
```python
# ❌ CURRENT (WRONG)
return {
    "success": True,
    "message": "Driver registered successfully...",
    "driver_id": str(new_driver.id),
    "phone_number": new_driver.phone_number,  # ← ENCRYPTED!
    "next_step": "verify_otp"
}

# ✅ FIX
return {
    "success": True,
    "message": "Driver registered successfully...",
    "driver_id": str(new_driver.id),
    "phone_number": phone_number,  # ← Use original plaintext
    "next_step": "verify_otp"
}
```

### Issue 2: Admin Registration Response (Line 577)
```python
# ❌ CURRENT (WRONG)
return {
    "success": True,
    "message": "Admin registered successfully...",
    "admin_id": str(new_admin.id),
    "phone_number": new_admin.phone_number,  # ← ENCRYPTED!
    "next_step": "verify_otp"
}

# ✅ FIX
return {
    "success": True,
    "message": "Admin registered successfully...",
    "admin_id": str(new_admin.id),
    "phone_number": admin_data.phone_number,  # ← Use original plaintext
    "next_step": "verify_otp"
}
```

### Issue 3: Customer Registration Response (Line 96)
```python
# ❌ CURRENT (WRONG)
return {
    "success": True,
    "message": "Customer registered successfully...",
    "customer_id": str(new_customer.id),
    "phone_number": new_customer.phone_number,  # ← ENCRYPTED!
    "next_step": "verify_otp"
}

# ✅ FIX
return {
    "success": True,
    "message": "Customer registered successfully...",
    "customer_id": str(new_customer.id),
    "phone_number": customer_data.phone_number,  # ← Use original plaintext
    "next_step": "verify_otp"
}
```

## 📝 COMPLETE FIX

Apply these changes to `core/routers/auth.py`:
