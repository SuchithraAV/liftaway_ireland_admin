from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
from core.utils.security import get_password_hash, create_access_token, create_refresh_token
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone
import secrets
import string
import logging
from typing import Optional
from uuid import UUID

router = APIRouter()
logger = logging.getLogger(__name__)

# Schemas
class DriverRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')

class AdminRegisterRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')

class VerifyOTPRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    otp: str = Field(..., pattern=r'^\d{6}$')

class LoginRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')

def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))

async def send_sms_otp(phone_number: str, otp_code: str) -> bool:
    """Mock SMS sending - replace with actual SMS service"""
    logger.info(f"Sending OTP {otp_code} to {phone_number}")
    return True

# Driver Registration
@router.post("/api/driver/register")
async def register_driver(
    request: DriverRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register driver and send OTP"""
    try:
        # Check if phone number exists
        result = await db.execute(select(Driver).where(Driver.phone_number == request.phone_number))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already registered")
        
        # Check if email exists
        result = await db.execute(select(Driver).where(Driver.email == request.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Generate OTP and expiry
        otp = generate_otp()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Create driver with is_phone_verified = false
        driver = Driver(
            full_name=request.name,
            email=request.email,
            phone_number=request.phone_number,
            password=get_password_hash("temp_password"),  # Temp password
            is_phone_verified=False,
            phone_otp=otp,
            otp_expires_at=expiry
        )
        
        # Create Stripe account automatically
        try:
            from core.services.stripe_connect import stripe_connect_service
            from core.models import DriverBankDetail
            
            # Create temporary bank detail object for Stripe setup
            temp_bank_detail = DriverBankDetail(
                bank_account_number="", # No bank details yet
                bank_ifsc="",
                account_holder_name=request.name
            )
            
            # Create Stripe account
            stripe_result = stripe_connect_service.create_custom_account(
                driver=driver,
                bank_detail=temp_bank_detail,
                country="IE",  # Default to IE for EUR
                ip_address="127.0.0.1"  # Should get from request
            )
            
            driver.stripe_account_id = stripe_result["stripe_account_id"]
            driver.stripe_verification_status = stripe_result.get("status", "pending")
            driver.stripe_payouts_enabled = stripe_result.get("payouts_enabled", False)
            driver.stripe_requirements_due = bool(stripe_result.get("requirements", {}).get("currently_due"))
                
        except Exception as e:
            logger.error(f"Failed to create Stripe account during registration: {e}")
            # Continue registration even if Stripe fails - can be set up later
        
        db.add(driver)
        await db.commit()
        await db.refresh(driver)
        
        # Send OTP
        await send_sms_otp(request.phone_number, otp)
        
        return {
            "success": True,
            "message": "Driver registered successfully. OTP sent to mobile number.",
            "user_id": str(driver.id),
            "phone_number": request.phone_number,
            "user": {
                "name": request.name,
                "email": request.email,
                "is_verified": False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver registration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

# Admin Registration
@router.post("/api/admin/register")
async def register_admin(
    request: AdminRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register admin and send OTP"""
    try:
        # Check if phone number exists
        result = await db.execute(select(Admin).where(Admin.phone_number == request.phone_number))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already registered")
        
        # Generate OTP and expiry
        otp = generate_otp()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Create admin with is_phone_verified = false
        admin = Admin(
            phone_number=request.phone_number,
            password=get_password_hash("temp_password"),  # Temp password
            is_phone_verified=False,
            phone_otp=otp,
            otp_expires_at=expiry
        )
        
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        
        # Send OTP
        await send_sms_otp(request.phone_number, otp)
        
        return {
            "success": True,
            "message": "Admin registered successfully. OTP sent to mobile number.",
            "user_id": str(admin.id),
            "phone_number": request.phone_number,
            "user": {
                "phone_number": request.phone_number,
                "is_verified": False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin registration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

# Driver Verify Registration
@router.post("/api/driver/verify-register")
async def verify_driver_register(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify driver registration OTP"""
    try:
        # Find driver
        result = await db.execute(select(Driver).where(Driver.phone_number == request.phone_number))
        driver = result.scalar_one_or_none()
        
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Check OTP
        if not driver.phone_otp or driver.phone_otp != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        # Check expiry
        if not driver.otp_expires_at or driver.otp_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="OTP expired")
        
        # Verify driver
        driver.is_phone_verified = True
        driver.phone_otp = None
        driver.otp_expires_at = None
        
        await db.commit()
        
        return {
            "success": True,
            "message": "OTP verified successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver OTP verification error: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

# Admin Verify Registration
@router.post("/api/admin/verify-register")
async def verify_admin_register(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify admin registration OTP"""
    try:
        # Find admin
        result = await db.execute(select(Admin).where(Admin.phone_number == request.phone_number))
        admin = result.scalar_one_or_none()
        
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        
        # Check OTP
        if not admin.phone_otp or admin.phone_otp != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        # Check expiry
        if not admin.otp_expires_at or admin.otp_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="OTP expired")
        
        # Verify admin
        admin.is_phone_verified = True
        admin.phone_otp = None
        admin.otp_expires_at = None
        
        await db.commit()
        
        return {
            "success": True,
            "message": "OTP verified successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin OTP verification error: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

# Driver Login
@router.post("/api/driver/login")
async def driver_login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Driver login - send OTP to verified driver"""
    try:
        # Find driver
        result = await db.execute(select(Driver).where(Driver.phone_number == request.phone_number))
        driver = result.scalar_one_or_none()
        
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        if not driver.is_phone_verified:
            raise HTTPException(status_code=400, detail="Driver not verified")
        
        # Generate OTP and expiry
        otp = generate_otp()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Save OTP
        driver.phone_otp = otp
        driver.otp_expires_at = expiry
        
        await db.commit()
        
        # Send OTP
        await send_sms_otp(request.phone_number, otp)
        
        return {
            "success": True,
            "message": "OTP sent to phone number.",
            "phone_number": request.phone_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")

# Admin Login
@router.post("/api/admin/login")
async def admin_login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Admin login - send OTP to verified admin"""
    try:
        # Find admin
        result = await db.execute(select(Admin).where(Admin.phone_number == request.phone_number))
        admin = result.scalar_one_or_none()
        
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        
        if not admin.is_phone_verified:
            raise HTTPException(status_code=400, detail="Admin not verified")
        
        # Generate OTP and expiry
        otp = generate_otp()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Save OTP
        admin.phone_otp = otp
        admin.otp_expires_at = expiry
        
        await db.commit()
        
        # Send OTP
        await send_sms_otp(request.phone_number, otp)
        
        return {
            "success": True,
            "message": "OTP sent to phone number.",
            "phone_number": request.phone_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")

# Driver Verify Login
@router.post("/api/driver/verify-login")
async def verify_driver_login(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify driver login OTP and return tokens"""
    try:
        # Find driver
        result = await db.execute(select(Driver).where(Driver.phone_number == request.phone_number))
        driver = result.scalar_one_or_none()
        
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Check OTP
        if not driver.phone_otp or driver.phone_otp != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        # Check expiry
        if not driver.otp_expires_at or driver.otp_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="OTP expired")
        
        # Generate tokens
        token_data = {"sub": str(driver.id), "phone": driver.phone_number, "role": "driver"}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        # Clear OTP
        driver.phone_otp = None
        driver.otp_expires_at = None
        
        await db.commit()
        
        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "user_id": str(driver.id),
                "name": driver.full_name,
                "email": driver.email,
                "phone_number": driver.phone_number,
                "is_verified": driver.is_phone_verified
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver login verification error: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Login verification failed: {str(e)}")

# Admin Verify Login
@router.post("/api/admin/verify-login")
async def verify_admin_login(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify admin login OTP and return tokens"""
    try:
        # Find admin
        result = await db.execute(select(Admin).where(Admin.phone_number == request.phone_number))
        admin = result.scalar_one_or_none()
        
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        
        # Check OTP
        if not admin.phone_otp or admin.phone_otp != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        # Check expiry
        if not admin.otp_expires_at or admin.otp_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="OTP expired")
        
        # Generate tokens
        token_data = {"sub": str(admin.id), "phone": admin.phone_number, "role": "admin"}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        # Clear OTP
        admin.phone_otp = None
        admin.otp_expires_at = None
        
        await db.commit()
        
        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "user_id": str(admin.id),
                "phone_number": admin.phone_number,
                "is_verified": admin.is_phone_verified
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin login verification error: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Login verification failed: {str(e)}")

# Debug endpoints
@router.get("/api/debug/driver/{phone_number}")
async def debug_driver(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Debug endpoint to check driver data"""
    try:
        result = await db.execute(select(Driver).where(Driver.phone_number == phone_number))
        driver = result.scalar_one_or_none()
        
        if not driver:
            return {"error": "Driver not found"}
        
        return {
            "id": str(driver.id),
            "name": driver.full_name,
            "email": driver.email,
            "phone_number": driver.phone_number,
            "is_verified": driver.is_phone_verified,
            "phone_otp": driver.phone_otp,
            "otp_expires_at": str(driver.otp_expires_at) if driver.otp_expires_at else None,
            "current_time": str(datetime.now(timezone.utc))
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/debug/admin/{phone_number}")
async def debug_admin(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Debug endpoint to check admin data"""
    try:
        result = await db.execute(select(Admin).where(Admin.phone_number == phone_number))
        admin = result.scalar_one_or_none()
        
        if not admin:
            return {"error": "Admin not found"}
        
        return {
            "id": str(admin.id),
            "phone_number": admin.phone_number,
            "is_verified": admin.is_phone_verified,
            "phone_otp": admin.phone_otp,
            "otp_expires_at": str(admin.otp_expires_at) if admin.otp_expires_at else None,
            "current_time": str(datetime.now(timezone.utc))
        }
    except Exception as e:
        return {"error": str(e)}
