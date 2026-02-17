from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin, OTPVerification as OTPModel
from core.auth import get_password_hash
from datetime import datetime, timedelta, timezone, date
import secrets
import string
import logging
import os
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID

router = APIRouter()
logger = logging.getLogger(__name__)

def generate_otp() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(6))

async def send_sms_otp(phone_number: str, otp_code: str) -> bool:
    logger.info(f"Sending OTP {otp_code} to {phone_number}")
    return True

async def save_uploaded_file(file: UploadFile, directory: str) -> str:
    if not file:
        return None
    os.makedirs(f"uploads/{directory}", exist_ok=True)
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    unique_filename = f"{secrets.token_hex(16)}.{file_extension}"
    file_path = f"uploads/{directory}/{unique_filename}"
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    return file_path

class AdminRegistration(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')

class OTPVerification(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    otp_code: str = Field(..., pattern=r'^\d{6}$')
    user_type: str = Field(..., pattern=r'^(driver|admin)$')
    action_type: str = Field(..., pattern=r'^(registration|login)$')

class ResendOTP(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    user_type: str = Field(..., pattern=r'^(driver|admin)$')
    action_type: str = Field(..., pattern=r'^(registration|login)$')

@router.post("/api/auth/register/driver/")
async def register_driver(
    # Personal Details
    full_name: str = Form(...),
    phone_number: str = Form(...),
    email: str = Form(...),
    date_of_birth: str = Form(...),
    address: str = Form(...),
    password: str = Form(...),
    
    # Identity Verification
    govt_id_type: str = Form(...),
    govt_id_number: str = Form(...),
    id_photo: Optional[UploadFile] = File(None),
    selfie_photo: Optional[UploadFile] = File(None),
    
    # Professional Details
    years_of_experience: int = Form(...),
    license_number: str = Form(...),
    license_category: str = Form(...),
    license_expiry_date: str = Form(...),
    previous_company: Optional[str] = Form(None),
    
    # Vehicle Details
    vehicle_type: str = Form(...),
    vehicle_number_plate: str = Form(...),
    vehicle_model: str = Form(...),
    vehicle_capacity: str = Form(...),
    rc_book_pic: Optional[UploadFile] = File(None),
    pollution_certificate_pic: Optional[UploadFile] = File(None),
    
    # Service Area Details
    pincodes: str = Form(...),
    preferred_shift: str = Form(...),
    
    # Bank/Payment Details (UK format)
    bank_account_number: str = Form(...),
    ifsc: str = Form(...),  # Using IFSC as sort code equivalent
    account_holder_name: str = Form(...),
    upi_id: Optional[str] = Form(None),
    
    # Document Upload (Required)
    driver_photo: UploadFile = File(...),
    license_front: UploadFile = File(...),
    license_back: UploadFile = File(...),
    vehicle_photo: UploadFile = File(...),
    
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Driver).where(Driver.phone_number == phone_number))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone number already registered")
    
    result = await db.execute(select(Driver).where(Driver.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Save uploaded files
    id_photo_path = await save_uploaded_file(id_photo, "driver_documents/id_photos") if id_photo else None
    selfie_photo_path = await save_uploaded_file(selfie_photo, "driver_documents/selfies") if selfie_photo else None
    rc_book_pic_path = await save_uploaded_file(rc_book_pic, "driver_documents/rc_books") if rc_book_pic else None
    pollution_cert_path = await save_uploaded_file(pollution_certificate_pic, "driver_documents/pollution_certs") if pollution_certificate_pic else None
    
    driver_photo_path = await save_uploaded_file(driver_photo, "driver_documents/photos")
    license_front_path = await save_uploaded_file(license_front, "driver_documents/license_front")
    license_back_path = await save_uploaded_file(license_back, "driver_documents/license_back")
    vehicle_photo_path = await save_uploaded_file(vehicle_photo, "driver_documents/vehicle_photos")
    
    dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    license_expiry = datetime.strptime(license_expiry_date, "%Y-%m-%d").date()
    
    hashed_password = get_password_hash(password)
    driver = Driver(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        dob=dob,
        address=address,
        password=hashed_password,
        govt_id_type=govt_id_type,
        govt_id_number=govt_id_number,
        id_photo_url=id_photo_path,
        selfie_photo_url=selfie_photo_path,
        years_experience=years_of_experience,
        license_number=license_number,
        license_category=license_category,
        license_expiry_date=license_expiry,
        previous_company=previous_company,
        vehicle_type=vehicle_type,
        vehicle_number_plate=vehicle_number_plate,
        vehicle_model=vehicle_model,
        vehicle_capacity=vehicle_capacity,
        rc_book_pic_url=rc_book_pic_path,
        pollution_cert_pic_url=pollution_cert_path,
        service_pincodes=pincodes,
        preferred_shift=preferred_shift,
        bank_account_number=bank_account_number,
        bank_ifsc=ifsc,
        account_holder_name=account_holder_name,
        upi_id=upi_id,
        driver_photo_url=driver_photo_path,
        license_front_url=license_front_path,
        license_back_url=license_back_path,
        vehicle_photo_url=vehicle_photo_path
    )
    
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    
    otp_code = generate_otp()
    otp = OTPModel(
        phone_number=phone_number,
        otp_code=otp_code,
        user_type="driver",
        action_type="registration",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.add(otp)
    await db.commit()
    await send_sms_otp(phone_number, otp_code)
    
    return {
        "success": True,
        "message": "Driver registered successfully. OTP sent to mobile number.",
        "user_id": driver.id,
        "phone_number": phone_number
    }

@router.post("/api/auth/register/admin/")
async def register_admin(admin_data: AdminRegistration, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Admin).where(Admin.phone_number == admin_data.phone_number))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone number already registered")
    
    hashed_password = get_password_hash(admin_data.password)
    admin = Admin(
        phone_number=admin_data.phone_number,
        password=hashed_password
    )
    
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    
    otp_code = generate_otp()
    otp = OTPModel(
        phone_number=admin_data.phone_number,
        otp_code=otp_code,
        user_type="admin",
        action_type="registration",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.add(otp)
    await db.commit()
    await send_sms_otp(admin_data.phone_number, otp_code)
    
    return {
        "success": True,
        "message": "Admin registered successfully. OTP sent to mobile number.",
        "user_id": admin.id,
        "phone_number": admin.phone_number
    }

@router.post("/api/auth/login/driver/")
async def driver_login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Driver).where(Driver.phone_number == login_data.phone_number))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found with this phone number")
    
    otp_code = generate_otp()
    otp = OTPModel(
        phone_number=login_data.phone_number,
        otp_code=otp_code,
        user_type="driver",
        action_type="login",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.add(otp)
    await db.commit()
    await send_sms_otp(login_data.phone_number, otp_code)
    
    return {
        "success": True,
        "message": "OTP sent to mobile number for login",
        "phone_number": login_data.phone_number
    }

@router.post("/api/auth/login/admin/")
async def admin_login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Admin).where(Admin.phone_number == login_data.phone_number))
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found with this phone number")
    
    otp_code = generate_otp()
    otp = OTPModel(
        phone_number=login_data.phone_number,
        otp_code=otp_code,
        user_type="admin",
        action_type="login",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.add(otp)
    await db.commit()
    await send_sms_otp(login_data.phone_number, otp_code)
    
    return {
        "success": True,
        "message": "OTP sent to mobile number for login",
        "phone_number": login_data.phone_number
    }

@router.post("/api/auth/verify-otp/")
async def verify_otp(otp_data: OTPVerification, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OTPModel)
        .where(
            OTPModel.phone_number == otp_data.phone_number,
            OTPModel.user_type == otp_data.user_type,
            OTPModel.action_type == otp_data.action_type,
            OTPModel.is_verified == False
        )
        .order_by(OTPModel.created_at.desc())
    )
    otp = result.scalar_one_or_none()
    
    if not otp:
        raise HTTPException(status_code=404, detail="No OTP found for verification")
    
    if otp.is_valid(otp_data.otp_code):
        otp.is_verified = True
        await db.commit()
        
        user_data = None
        if otp_data.action_type == "registration":
            if otp_data.user_type == "driver":
                result = await db.execute(select(Driver).where(Driver.phone_number == otp_data.phone_number))
                driver = result.scalar_one_or_none()
                if driver:
                    driver.is_phone_verified = True
                    await db.commit()
                    user_data = {"id": str(driver.id), "full_name": driver.full_name, "email": driver.email}
            elif otp_data.user_type == "admin":
                result = await db.execute(select(Admin).where(Admin.phone_number == otp_data.phone_number))
                admin = result.scalar_one_or_none()
                if admin:
                    admin.is_phone_verified = True
                    await db.commit()
                    user_data = {"id": str(admin.id), "phone_number": admin.phone_number}
        
        return {
            "success": True,
            "message": f"OTP verified successfully for {otp_data.action_type}",
            "user_type": otp_data.user_type,
            "action_type": otp_data.action_type,
            "user_data": user_data
        }
    
    elif otp.is_expired():
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
    else:
        raise HTTPException(status_code=400, detail="Invalid OTP code")

@router.post("/api/auth/resend-otp/")
async def resend_otp(resend_data: ResendOTP, db: AsyncSession = Depends(get_db)):
    user_exists = False
    if resend_data.user_type == "driver":
        result = await db.execute(select(Driver).where(Driver.phone_number == resend_data.phone_number))
        user_exists = result.scalar_one_or_none() is not None
    elif resend_data.user_type == "admin":
        result = await db.execute(select(Admin).where(Admin.phone_number == resend_data.phone_number))
        user_exists = result.scalar_one_or_none() is not None
    
    if not user_exists:
        raise HTTPException(status_code=404, detail=f"{resend_data.user_type.title()} not found with this phone number")
    
    otp_code = generate_otp()
    otp = OTPModel(
        phone_number=resend_data.phone_number,
        otp_code=otp_code,
        user_type=resend_data.user_type,
        action_type=resend_data.action_type,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.add(otp)
    await db.commit()
    await send_sms_otp(resend_data.phone_number, otp_code)
    
    return {
        "success": True,
        "message": "New OTP sent to mobile number",
        "phone_number": resend_data.phone_number
    }