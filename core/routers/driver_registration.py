from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Customer, Admin, DriverDocument, DriverBankDetail, DriverVehicle
from core.utils.security import get_password_hash
from core.utils.twilio_service import twilio_service
from core.utils.s3_upload import upload_file_to_s3, get_full_url
from datetime import datetime, timedelta
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Driver Registration"])


@router.post("/register/driver/upload", status_code=status.HTTP_201_CREATED)
async def register_driver_with_upload(
    # Personal Details
    full_name: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    
    # Identity Verification
    govt_id_type: Optional[str] = Form(None),
    govt_id_number: Optional[str] = Form(None),
    
    # Professional Details
    years_of_experience: Optional[int] = Form(None),
    license_number: Optional[str] = Form(None),
    license_category: Optional[str] = Form(None),
    license_expiry_date: Optional[str] = Form(None),
    
    # Vehicle Details
    vehicle_type: Optional[str] = Form(None),
    vehicle_number: Optional[str] = Form(None),
    vehicle_model: Optional[str] = Form(None),
    vehicle_capacity: Optional[str] = Form(None),
    
    # Service Area
    pincodes: Optional[str] = Form(None),
    preferred_shift: Optional[str] = Form(None),
    
    # Bank Details
    account_number: Optional[str] = Form(None),
    sort_code: Optional[str] = Form(None),
    holder_name: Optional[str] = Form(None),
    upi_id: Optional[str] = Form(None),
    
    # File Uploads
    driver_photo: UploadFile = File(default=None),
    license_front: UploadFile = File(default=None),
    license_back: UploadFile = File(default=None),
    govt_id_photo: UploadFile = File(default=None),
    selfie_photo: UploadFile = File(default=None),
    vehicle_photo: UploadFile = File(default=None),
    rc_book_photo: UploadFile = File(default=None),
    pollution_certificate_photo: UploadFile = File(default=None),
    
    db: AsyncSession = Depends(get_db)
):
    """Register new driver with file uploads to Utho Object Storage"""
    
    logger.info(f"🔐 Driver registration with upload for phone: {phone_number}")
    
    # Check if phone or email exists
    from core.utils.field_encryption import encrypt_email, encrypt_phone
    
    encrypted_phone = encrypt_phone(phone_number) if phone_number else None
    encrypted_email = encrypt_email(email) if email else None
    
    for model in [Customer, Driver, Admin]:
        if encrypted_phone and hasattr(model, 'phone_number'):
            result = await db.execute(select(model).where(model.phone_number == encrypted_phone))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
        if encrypted_email and hasattr(model, 'email'):
            result = await db.execute(select(model).where(model.email == encrypted_email))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
    
    # Parse dates
    try:
        dob_date = datetime.strptime(dob, "%Y-%m-%d") if dob else None
        license_expiry = datetime.strptime(license_expiry_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    # Create driver first to get ID for folder structure
    from core.utils.field_encryption import encrypt_field, encrypt_email, encrypt_phone, encrypt_address, encrypt_govt_id, encrypt_bank_account
    
    new_driver = Driver(
        full_name=encrypt_field(full_name) if full_name else None,
        phone_number=encrypt_phone(phone_number) if phone_number else None,
        email=encrypt_email(email) if email else None,
        dob=dob_date,
        address=encrypt_address(address) if address else None,
        years_experience=years_of_experience,
        service_pincodes=pincodes,
        preferred_shift=preferred_shift,
        password=get_password_hash(password) if password else None,
        is_active=True,
        is_approved="pending",
        is_phone_verified=False
    )
    
    db.add(new_driver)
    await db.commit()
    await db.refresh(new_driver)
    
    driver_id = str(new_driver.id)
    
    try:
        # Upload files to Utho Object Storage with driver-specific folder
        logger.info(f"📤 Uploading files for driver {driver_id}")
        
        driver_photo_url = await upload_file_to_s3(driver_photo, driver_id, "driver_photo") if driver_photo and driver_photo.filename else None
        license_front_url = await upload_file_to_s3(license_front, driver_id, "license_front") if license_front and license_front.filename else None
        license_back_url = await upload_file_to_s3(license_back, driver_id, "license_back") if license_back and license_back.filename else None
        govt_id_photo_url = await upload_file_to_s3(govt_id_photo, driver_id, "govt_id") if govt_id_photo and govt_id_photo.filename else None
        selfie_photo_url = await upload_file_to_s3(selfie_photo, driver_id, "selfie") if selfie_photo and selfie_photo.filename else None
        vehicle_photo_url = await upload_file_to_s3(vehicle_photo, driver_id, "vehicle") if vehicle_photo and vehicle_photo.filename else None
        rc_book_url = await upload_file_to_s3(rc_book_photo, driver_id, "rc_book") if rc_book_photo and rc_book_photo.filename else None
        pollution_cert_url = await upload_file_to_s3(pollution_certificate_photo, driver_id, "pollution_cert") if pollution_certificate_photo and pollution_certificate_photo.filename else None
        
        # Create driver documents record
        driver_doc = DriverDocument(
            driver_id=new_driver.id,
            govt_id_type=govt_id_type,
            govt_id_number=encrypt_govt_id(govt_id_number) if govt_id_number else None,
            id_photo_url=get_full_url(govt_id_photo_url),
            selfie_photo_url=get_full_url(selfie_photo_url),
            license_number=encrypt_field(license_number) if license_number else None,
            license_category=license_category,
            license_expiry_date=license_expiry,
            license_front_url=get_full_url(license_front_url),
            license_back_url=get_full_url(license_back_url),
            driver_photo_url=get_full_url(driver_photo_url)
        )
        
        # Create vehicle record
        driver_vehicle = DriverVehicle(
            driver_id=new_driver.id,
            vehicle_type=vehicle_type,
            vehicle_number_plate=encrypt_field(vehicle_number) if vehicle_number else None,
            vehicle_model=vehicle_model,
            vehicle_capacity=vehicle_capacity,
            vehicle_photo_url=get_full_url(vehicle_photo_url),
            rc_book_pic_url=get_full_url(rc_book_url),
            pollution_cert_pic_url=get_full_url(pollution_cert_url)
        )
        
        # Create bank details record
        driver_bank = DriverBankDetail(
            driver_id=new_driver.id,
            bank_account_number=encrypt_bank_account(account_number) if account_number else None,
            bank_ifsc=encrypt_field(sort_code) if sort_code else None,
            account_holder_name=encrypt_field(holder_name) if holder_name else None,
            upi_id=encrypt_field(upi_id) if upi_id else None
        )
        
        db.add(driver_doc)
        db.add(driver_vehicle)
        db.add(driver_bank)
        await db.commit()
        
        logger.info(f"✅ Files uploaded and records created for driver {driver_id}")
        
        # Send OTP
        if twilio_service:
            twilio_result = twilio_service.send_otp(phone_number)
            if not twilio_result["success"]:
                logger.warning(f"⚠️ OTP send failed but registration completed: {twilio_result.get('error')}")
        else:
            logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
            new_driver.phone_otp = "123456"
            new_driver.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
            await db.commit()
        
        return {
            "success": True,
            "message": "Driver registered successfully with documents uploaded",
            "driver_id": driver_id,
            "phone_number": phone_number,
            "documents_uploaded": {
                "driver_photo": get_full_url(driver_photo_url),
                "license_front": get_full_url(license_front_url),
                "license_back": get_full_url(license_back_url),
                "govt_id": get_full_url(govt_id_photo_url),
                "selfie": get_full_url(selfie_photo_url),
                "vehicle": get_full_url(vehicle_photo_url),
                "rc_book": get_full_url(rc_book_url),
                "pollution_cert": get_full_url(pollution_cert_url)
            },
            "next_step": "verify_otp"
        }
        
    except Exception as e:
        logger.error(f"❌ Error during driver registration: {str(e)}")
        # Rollback driver creation if file upload fails
        await db.delete(new_driver)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )
