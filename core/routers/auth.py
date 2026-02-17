from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import UserRole, Customer, Driver, Admin
from core.utils.field_encryption import encrypt_email, decrypt_email, encrypt_phone, decrypt_phone, encrypt_field, decrypt_field, encrypt_address, decrypt_address, encrypt_bank_account, decrypt_bank_account, encrypt_govt_id, decrypt_govt_id
from core.schemas import (
    CustomerCreate, DriverCreate, AdminCreate, UserResponse, LoginResponse, 
    SendOTPRequest, VerifyOTPRequest, ResendOTPRequest, MobileLoginRequest
)
from core.utils.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from core.utils.email import get_otp_expiry
from core.utils.twilio_service import twilio_service
from datetime import datetime, timedelta
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

# CUSTOMER REGISTRATION AND LOGIN

@router.post("/register/customer", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_customer(customer_data: CustomerCreate, db: AsyncSession = Depends(get_db)):
    '''Register new customer with comprehensive details'''
    logger.info(f"🔐 Customer registration attempt for phone: {customer_data.phone_number}")
    
    # Encrypt search terms
    encrypted_phone = encrypt_phone(customer_data.phone_number)
    encrypted_email = encrypt_email(customer_data.email)
    
    # Check if phone number or email exists
    for model in [Customer, Driver, Admin]:
        if hasattr(model, 'phone_number'):
            result = await db.execute(select(model).where(model.phone_number == encrypted_phone))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
        if hasattr(model, 'email'):
            result = await db.execute(select(model).where(model.email == encrypted_email))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
    
    # Hash password
    hashed_password = get_password_hash(customer_data.password)
    
    # Create new customer with encrypted data
    new_customer = Customer(
        full_name=encrypt_field(customer_data.full_name),
        email=encrypted_email,
        phone_number=encrypted_phone,
        address=encrypt_address(customer_data.address) if customer_data.address else None,
        password=hashed_password,
        is_active=True,
        is_email_verified=False,
        is_phone_verified=False
    )
    
    db.add(new_customer)
    await db.commit()
    await db.refresh(new_customer)
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        logger.info(f"📱 Attempting to send OTP to {customer_data.phone_number}")
        twilio_result = twilio_service.send_otp(customer_data.phone_number)
        logger.info(f"📱 Twilio result: {twilio_result}")
        if not twilio_result["success"]:
            error_msg = twilio_result.get('error', 'Unknown error')
            error_code = twilio_result.get('error_code', 'N/A')
            logger.error(f"❌ Twilio OTP failed: {error_msg} (Code: {error_code})")
            await db.delete(new_customer)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to send OTP: {error_msg}"
            )
    else:
        # Fallback for local testing without Twilio
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        new_customer.phone_otp = "123456"
        new_customer.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        logger.info("✅ Test OTP stored in database")
    
    return {
        "success": True,
        "message": "Customer registered successfully. OTP sent to your phone number.",
        "customer_id": str(new_customer.id),
        "phone_number": customer_data.phone_number,  # Return plaintext, not encrypted
        "next_step": "verify_otp"
    }

@router.post("/customer/send-otp")
async def send_customer_otp(request: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Send OTP to customer phone number using Twilio Verify'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Customer).where(Customer.phone_number == encrypted_phone))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return twilio_result
    else:
        # Fallback for local testing
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        customer.phone_otp = "123456"
        customer.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        return {
            "success": True,
            "message": "OTP sent successfully (TEST MODE - use 123456)",
            "phone_number": request.phone_number,
            "otp": "123456"
        }

@router.post("/customer/verify-otp")
async def verify_customer_otp(request: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Verify customer OTP using Twilio Verify and complete registration/login'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Customer).where(Customer.phone_number == encrypted_phone))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Verify OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.verify_otp(request.phone_number, request.otp)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Invalid or expired OTP")
            )
    else:
        # Fallback for local testing
        if not customer.phone_otp or customer.phone_otp != request.otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        if customer.otp_expires_at and datetime.utcnow() > customer.otp_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired"
            )
    
    # Mark as verified and clear OTP
    customer.is_phone_verified = True
    customer.phone_otp = None
    customer.otp_expires_at = None
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(customer.id), "role": UserRole.CUSTOMER.value})
    refresh_token = create_refresh_token(data={"sub": str(customer.id), "role": UserRole.CUSTOMER.value})
    
    user_response = UserResponse(
        id=customer.id,
        role=UserRole.CUSTOMER,
        is_active=customer.is_active,
        approval_status="approved",
        is_email_verified=customer.is_email_verified,
        is_phone_verified=customer.is_phone_verified,
        date_joined=customer.date_joined,
        full_name=decrypt_field(customer.full_name) if customer.full_name else None,
        email=decrypt_email(customer.email) if customer.email else None,
        phone_number=decrypt_phone(customer.phone_number)
    )
    
    return {
        "success": True,
        "message": "Phone number verified successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/customer"
    }

@router.post("/login/customer")
async def login_customer(request: MobileLoginRequest, db: AsyncSession = Depends(get_db)):
    '''Customer login with phone number - sends OTP via Twilio'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Customer).where(Customer.phone_number == encrypted_phone))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return {
            "success": True,
            "message": "OTP sent to your phone number",
            "phone_number": request.phone_number,
            "next_step": "verify_otp"
        }
    else:
        # Fallback for local testing
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        customer.phone_otp = "123456"
        customer.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        return {
            "success": True,
            "message": "OTP sent to your phone number (TEST MODE - use 123456)",
            "phone_number": request.phone_number,
            "otp": "123456",
            "next_step": "verify_otp"
        }

class EmailPasswordLogin(BaseModel):
    email: str
    password: str

@router.post("/login/customer/email")
async def login_customer_email(request: EmailPasswordLogin, db: AsyncSession = Depends(get_db)):
    '''Customer login with email and password'''
    encrypted_email = encrypt_email(request.email)
    result = await db.execute(select(Customer).where(Customer.email == encrypted_email))
    customer = result.scalar_one_or_none()
    
    if not customer or not verify_password(request.password, customer.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    access_token = create_access_token(data={"sub": str(customer.id), "role": UserRole.CUSTOMER.value})
    refresh_token = create_refresh_token(data={"sub": str(customer.id), "role": UserRole.CUSTOMER.value})
    
    user_response = UserResponse(
        id=customer.id,
        role=UserRole.CUSTOMER,
        is_active=customer.is_active,
        approval_status="approved",
        is_email_verified=customer.is_email_verified,
        is_phone_verified=customer.is_phone_verified,
        date_joined=customer.date_joined,
        full_name=decrypt_field(customer.full_name) if customer.full_name else None,
        email=decrypt_email(customer.email) if customer.email else None,
        phone_number=decrypt_phone(customer.phone_number)
    )
    
    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/customer"
    }

# DRIVER REGISTRATION AND LOGIN

@router.post("/register/driver", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_driver(driver_data: DriverCreate, db: AsyncSession = Depends(get_db)):
    '''Register new driver with comprehensive details'''
    logger.info(f"🔐 Driver registration attempt for phone: {driver_data.personal_details.phone_number}")
    
    # Encrypt search terms
    phone_number = driver_data.personal_details.phone_number
    email = driver_data.personal_details.email
    encrypted_phone = encrypt_phone(phone_number)
    encrypted_email = encrypt_email(email)
    
    for model in [Customer, Driver, Admin]:
        if hasattr(model, 'phone_number'):
            result = await db.execute(select(model).where(model.phone_number == encrypted_phone))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
        if hasattr(model, 'email'):
            result = await db.execute(select(model).where(model.email == encrypted_email))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
    
    # Hash password
    hashed_password = get_password_hash(driver_data.password)
    
    # Parse dates
    dob = None
    license_expiry = None
    try:
        if driver_data.personal_details.dob:
            dob = datetime.strptime(driver_data.personal_details.dob, "%Y-%m-%d")
        license_expiry = datetime.strptime(driver_data.professional_details.license_expiry_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    # Create new driver with encrypted data
    new_driver = Driver(
        # Personal Details
        full_name=encrypt_field(driver_data.personal_details.full_name),
        phone_number=encrypted_phone,
        email=encrypted_email,
        dob=dob,
        address=encrypt_address(driver_data.personal_details.address) if driver_data.personal_details.address else None,
        
        # Identity Verification
        govt_id_type=driver_data.identity_verification.govt_id_type,
        govt_id_number=encrypt_govt_id(driver_data.identity_verification.govt_id_number),
        id_photo_url=driver_data.identity_verification.id_photo_url,
        selfie_photo_url=driver_data.identity_verification.selfie_photo_url,
        
        # Professional Details
        years_experience=driver_data.professional_details.years_experience,
        license_number=driver_data.professional_details.license_number,
        license_category=driver_data.professional_details.license_category,
        license_expiry_date=license_expiry,

        
        # Vehicle Details
        vehicle_type=driver_data.vehicle_details.vehicle_type,
        vehicle_number_plate=driver_data.vehicle_details.vehicle_number_plate,
        vehicle_model=driver_data.vehicle_details.vehicle_model,
        vehicle_capacity=driver_data.vehicle_details.vehicle_capacity,
        rc_book_pic_url=driver_data.vehicle_details.rc_book_pic_url,
        pollution_cert_pic_url=driver_data.vehicle_details.pollution_cert_pic_url,
        
        # Service Area Details
        service_pincodes=driver_data.service_area_details.service_pincodes,
        preferred_shift=driver_data.service_area_details.preferred_shift,
        
        # Bank Details
        bank_account_number=encrypt_bank_account(driver_data.bank_details.bank_account_number),
        bank_ifsc=driver_data.bank_details.bank_ifsc,
        account_holder_name=encrypt_field(driver_data.bank_details.account_holder_name),
        upi_id=driver_data.bank_details.upi_id,
        
        # Document Upload
        driver_photo_url=driver_data.document_upload.driver_photo_url,
        license_front_url=driver_data.document_upload.license_front_url,
        license_back_url=driver_data.document_upload.license_back_url,
        vehicle_photo_url=driver_data.document_upload.vehicle_photo_url,
        
        # System fields
        password=hashed_password,
        is_active=True,
        is_approved="pending",  # Requires admin approval
        is_phone_verified=False
    )
    
    # Create Stripe account automatically
    try:
        from core.services.stripe_connect import stripe_connect_service
        from core.models import DriverBankDetail, DriverDocument
        
        # Create temporary bank detail object for Stripe setup
        temp_bank_detail = DriverBankDetail(
            bank_account_number=driver_data.bank_details.bank_account_number,
            bank_ifsc=driver_data.bank_details.bank_ifsc,
            account_holder_name=driver_data.bank_details.account_holder_name
        )
        
        # Create Stripe account
        stripe_result = stripe_connect_service.create_custom_account(
            driver=new_driver,
            bank_detail=temp_bank_detail,
            country="IE",  # Default to IE for EUR
            ip_address="127.0.0.1"  # Should get from request
        )
        
        new_driver.stripe_account_id = stripe_result["stripe_account_id"]
        new_driver.stripe_verification_status = stripe_result.get("status", "pending")
        new_driver.stripe_payouts_enabled = stripe_result.get("payouts_enabled", False)
        new_driver.stripe_requirements_due = bool(stripe_result.get("requirements", {}).get("currently_due"))
        
        if driver_data.bank_details.bank_account_number:
            new_driver.stripe_bank_last4 = driver_data.bank_details.bank_account_number[-4:]
            
    except Exception as e:
        logger.error(f"Failed to create Stripe account during registration: {e}")
        # Continue registration even if Stripe fails - can be set up later
    
    db.add(new_driver)
    await db.commit()
    await db.refresh(new_driver)
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(phone_number)
        if not twilio_result["success"]:
            await db.delete(new_driver)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to send OTP: {twilio_result.get('error', 'Unknown error')}"
            )
    else:
        # Fallback for local testing without Twilio
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        new_driver.phone_otp = "123456"
        new_driver.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
    
    return {
        "success": True,
        "message": "Driver registered successfully. OTP sent to your phone number. Account pending admin approval.",
        "driver_id": str(new_driver.id),
        "phone_number": phone_number,  # Return plaintext, not encrypted
        "next_step": "verify_otp"
    }

@router.post("/driver/send-otp")
async def send_driver_otp(request: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Send OTP to driver phone number using Twilio Verify'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Driver).where(Driver.phone_number == encrypted_phone))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Send OTP via Twilio Verify
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return twilio_result
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service is not available"
        )

@router.post("/driver/verify-otp")
async def verify_driver_otp(request: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Verify driver OTP using Twilio Verify and complete registration/login'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Driver).where(Driver.phone_number == encrypted_phone))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Verify OTP via Twilio Verify
    if twilio_service:
        twilio_result = twilio_service.verify_otp(request.phone_number, request.otp)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Invalid or expired OTP")
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service is not available"
        )
    
    # Mark as verified and clear OTP
    driver.is_phone_verified = True
    driver.phone_otp = None
    driver.otp_expires_at = None
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(driver.id), "role": UserRole.DRIVER.value})
    refresh_token = create_refresh_token(data={"sub": str(driver.id), "role": UserRole.DRIVER.value})
    
    user_response = UserResponse(
        id=driver.id,
        role=UserRole.DRIVER,
        is_active=driver.is_active,
        approval_status=driver.approval_status,
        is_email_verified=False,
        is_phone_verified=driver.is_phone_verified,
        date_joined=driver.date_joined,
        full_name=decrypt_field(driver.full_name) if driver.full_name else None,
        email=decrypt_email(driver.email) if driver.email else None,
        phone_number=decrypt_phone(driver.phone_number)
    )
    
    return {
        "success": True,
        "message": "Phone number verified successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/driver"
    }

@router.post("/login/driver")
async def login_driver(request: MobileLoginRequest, db: AsyncSession = Depends(get_db)):
    '''Driver login with phone number - sends OTP via Twilio'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Driver).where(Driver.phone_number == encrypted_phone))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    if not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Send OTP via Twilio Verify
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return {
            "success": True,
            "message": "OTP sent to your phone number",
            "phone_number": request.phone_number,
            "next_step": "verify_otp"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service is not available"
        )

@router.post("/login/driver/email")
async def login_driver_email(request: EmailPasswordLogin, db: AsyncSession = Depends(get_db)):
    '''Driver login with email and password'''
    encrypted_email = encrypt_email(request.email)
    result = await db.execute(select(Driver).where(Driver.email == encrypted_email))
    driver = result.scalar_one_or_none()
    
    if not driver or not verify_password(request.password, driver.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    access_token = create_access_token(data={"sub": str(driver.id), "role": UserRole.DRIVER.value})
    refresh_token = create_refresh_token(data={"sub": str(driver.id), "role": UserRole.DRIVER.value})
    
    user_response = UserResponse(
        id=driver.id,
        role=UserRole.DRIVER,
        is_active=driver.is_active,
        approval_status=driver.approval_status,
        is_email_verified=False,
        is_phone_verified=driver.is_phone_verified,
        date_joined=driver.date_joined,
        full_name=decrypt_field(driver.full_name) if driver.full_name else None,
        email=decrypt_email(driver.email) if driver.email else None,
        phone_number=decrypt_phone(driver.phone_number)
    )
    
    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/driver"
    }

# ADMIN REGISTRATION AND LOGIN

@router.post("/register/admin", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_admin(admin_data: AdminCreate, db: AsyncSession = Depends(get_db)):
    '''Register new admin with phone number and password'''
    logger.info(f"🔐 Admin registration attempt for phone: {admin_data.phone_number}")
    
    # Encrypt search term
    encrypted_phone = encrypt_phone(admin_data.phone_number)
    
    # Check if phone number exists
    for model in [Customer, Driver, Admin]:
        if hasattr(model, 'phone_number'):
            result = await db.execute(select(model).where(model.phone_number == encrypted_phone))
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
    
    # Hash password
    hashed_password = get_password_hash(admin_data.password)
    
    # Create new admin with encrypted data
    new_admin = Admin(
        phone_number=encrypted_phone,
        password=hashed_password,
        is_active=True,
        is_phone_verified=False
    )
    
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(admin_data.phone_number)
        if not twilio_result["success"]:
            await db.delete(new_admin)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to send OTP: {twilio_result.get('error', 'Unknown error')}"
            )
    else:
        # Fallback for local testing without Twilio
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        new_admin.phone_otp = "123456"
        new_admin.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
    
    return {
        "success": True,
        "message": "Admin registered successfully. OTP sent to your phone number.",
        "admin_id": str(new_admin.id),
        "phone_number": admin_data.phone_number,  # Return plaintext, not encrypted
        "next_step": "verify_otp"
    }

@router.post("/admin/send-otp")
async def send_admin_otp(request: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Send OTP to admin phone number using Twilio Verify'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Admin).where(Admin.phone_number == encrypted_phone))
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return twilio_result
    else:
        # Fallback for local testing
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        admin.phone_otp = "123456"
        admin.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        return {
            "success": True,
            "message": "OTP sent successfully (TEST MODE - use 123456)",
            "phone_number": request.phone_number,
            "otp": "123456"
        }

@router.post("/admin/verify-otp")
async def verify_admin_otp(request: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Verify admin OTP using Twilio Verify and complete registration/login'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Admin).where(Admin.phone_number == encrypted_phone))
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    # Verify OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.verify_otp(request.phone_number, request.otp)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Invalid or expired OTP")
            )
    else:
        # Fallback for local testing
        if not admin.phone_otp or admin.phone_otp != request.otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        if admin.otp_expires_at and datetime.utcnow() > admin.otp_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired"
            )
    
    # Mark as verified and clear OTP
    admin.is_phone_verified = True
    admin.phone_otp = None
    admin.otp_expires_at = None
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token(data={"sub": str(admin.id), "role": UserRole.ADMIN.value})
    refresh_token = create_refresh_token(data={"sub": str(admin.id), "role": UserRole.ADMIN.value})
    
    user_response = UserResponse(
        id=admin.id,
        role=UserRole.ADMIN,
        is_active=admin.is_active,
        approval_status="approved",
        is_phone_verified=admin.is_phone_verified,
        date_joined=admin.date_joined,
        phone_number=decrypt_phone(admin.phone_number)
    )
    
    return {
        "success": True,
        "message": "Phone number verified successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/admin"
    }

@router.post("/login/admin")
async def login_admin(request: MobileLoginRequest, db: AsyncSession = Depends(get_db)):
    '''Admin login with phone number - sends OTP via Twilio'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Admin).where(Admin.phone_number == encrypted_phone))
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered"
        )
    
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Send OTP via Twilio Verify (or use fallback for local testing)
    if twilio_service:
        twilio_result = twilio_service.send_otp(request.phone_number)
        if not twilio_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=twilio_result.get("error", "Failed to send OTP")
            )
        return {
            "success": True,
            "message": "OTP sent to your phone number",
            "phone_number": request.phone_number,
            "next_step": "verify_otp"
        }
    else:
        # Fallback for local testing
        logger.warning("⚠️ Twilio not configured - using test OTP: 123456")
        admin.phone_otp = "123456"
        admin.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        return {
            "success": True,
            "message": "OTP sent to your phone number (TEST MODE - use 123456)",
            "phone_number": request.phone_number,
            "otp": "123456",
            "next_step": "verify_otp"
        }

class PhonePasswordLogin(BaseModel):
    phone_number: str
    password: str

@router.post("/login/admin/password")
async def login_admin_password(request: PhonePasswordLogin, db: AsyncSession = Depends(get_db)):
    '''Admin login with phone number and password'''
    encrypted_phone = encrypt_phone(request.phone_number)
    result = await db.execute(select(Admin).where(Admin.phone_number == encrypted_phone))
    admin = result.scalar_one_or_none()
    
    if not admin or not verify_password(request.password, admin.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password"
        )
    
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    access_token = create_access_token(data={"sub": str(admin.id), "role": UserRole.ADMIN.value})
    refresh_token = create_refresh_token(data={"sub": str(admin.id), "role": UserRole.ADMIN.value})
    
    user_response = UserResponse(
        id=admin.id,
        role=UserRole.ADMIN,
        is_active=admin.is_active,
        approval_status="approved",
        is_phone_verified=admin.is_phone_verified,
        date_joined=admin.date_joined,
        phone_number=decrypt_phone(admin.phone_number)
    )
    
    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_response,
        "dashboard_url": "/dashboard/admin"
    }

# RESEND OTP ENDPOINTS

@router.post("/customer/resend-otp")
async def resend_customer_otp(request: ResendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Resend OTP to customer'''
    return await send_customer_otp(SendOTPRequest(phone_number=request.phone_number), db)

@router.post("/driver/resend-otp")
async def resend_driver_otp(request: ResendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Resend OTP to driver'''
    return await send_driver_otp(SendOTPRequest(phone_number=request.phone_number), db)

@router.post("/admin/resend-otp")
async def resend_admin_otp(request: ResendOTPRequest, db: AsyncSession = Depends(get_db)):
    '''Resend OTP to admin'''
    return await send_admin_otp(SendOTPRequest(phone_number=request.phone_number), db)