"""
Driver Stripe Connect Account Setup Endpoints

Provides:
- POST /driver/stripe/setup - Create Stripe Connected Account for driver
- GET /driver/stripe/status - Get Stripe account status
- POST /driver/stripe/update-bank - Update bank account details

Currency: EUR (Euros)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.dependencies import get_current_driver, get_current_driver_any_status
from core.models import Driver, DriverBankDetail, DriverDocument
from core.services.stripe_connect import stripe_connect_service
from pydantic import BaseModel, Field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/driver/stripe", tags=["Driver Stripe Connect"])


class StripeSetupRequest(BaseModel):
    """Request to setup Stripe account with bank details"""
    ip_address: Optional[str] = None
    country: str = Field(default="IE", description="Country code: IE for Ireland, DE for Germany (EUR countries)")
    # Bank details for setup
    dob: Optional[str] = Field(None, description="Date of birth YYYY-MM-DD")
    address: Optional[str] = None
    account_number: str = Field(..., description="IBAN for EUR countries")
    sort_code: str = Field(default="", description="Sort code/routing (optional for SEPA)")
    account_holder_name: str = Field(..., min_length=2, max_length=100)


class StripeSetupResponse(BaseModel):
    success: bool
    message: str
    stripe_account_id: Optional[str] = None
    verification_status: str
    payouts_enabled: bool


class BankUpdateRequest(BaseModel):
    """Update bank account details"""
    account_number: str = Field(..., min_length=6, max_length=34, description="IBAN for EUR")
    sort_code: str = Field(default="", max_length=11, description="Optional for SEPA")
    account_holder_name: str = Field(..., min_length=2, max_length=100)


class ManualLinkRequest(BaseModel):
    stripe_account_id: str


@router.post("/manual-link")
async def manual_link_account(
    request: ManualLinkRequest,
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually link an existing Stripe Connected Account ID to the driver.
    Useful for testing or if account was created outside the app.
    """
    # Verify the account exists on Stripe
    try:
        account_status = stripe_connect_service.get_account_status(request.stripe_account_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe Account ID or not connected: {str(e)}")

    current_driver.stripe_account_id = request.stripe_account_id
    current_driver.stripe_verification_status = account_status.get("verification_status", "unknown")
    current_driver.stripe_payouts_enabled = account_status.get("payouts_enabled", False)
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Linked Stripe account {request.stripe_account_id} to driver",
        "account_status": account_status
    }


@router.post("/unlink")
async def unlink_stripe_account(
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Unlink the current Stripe account from the driver.
    WARNING: This does not delete the Stripe account, only removes the link.
    Use for testing or switching account types.
    """
    if not current_driver.stripe_account_id:
        return {
            "success": False,
            "message": "No Stripe account linked"
        }
    
    old_account_id = current_driver.stripe_account_id
    
    # Clear Stripe fields
    current_driver.stripe_account_id = None
    current_driver.stripe_verification_status = None
    current_driver.stripe_payouts_enabled = False
    current_driver.stripe_requirements_due = False
    current_driver.stripe_bank_last4 = None
    
    await db.commit()
    
    logger.info(f"Unlinked Stripe account {old_account_id} from driver {current_driver.id}")
    
    return {
        "success": True,
        "message": f"Unlinked Stripe account {old_account_id}",
        "note": "The Stripe account still exists but is no longer linked to this driver"
    }



@router.post("/setup-express")
async def setup_express_account(
    http_request: Request,
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Stripe Express Connected Account for the driver.
    
    Express accounts provide:
    - Full Stripe Dashboard access (drivers can login to view their earnings)
    - Stripe-hosted onboarding (handles all verification)
    - Automatic payout management
    
    Returns an onboarding link for the driver to complete setup.
    """
    driver_id = current_driver.id
    
    # Check if driver already has a Stripe account
    if current_driver.stripe_account_id:
        return {
            "success": False,
            "message": "Driver already has a Stripe account",
            "stripe_account_id": current_driver.stripe_account_id
        }
    
    try:
        # Create Express account
        result = stripe_connect_service.create_express_account(
            driver=current_driver,
            country="IE"  # Default to Ireland, can be parameterized
        )
        
        # Update driver record
        current_driver.stripe_account_id = result["stripe_account_id"]
        current_driver.stripe_verification_status = "pending"
        current_driver.stripe_payouts_enabled = False
        
        await db.commit()
        
        # Generate onboarding link
        base_url = str(http_request.base_url).rstrip("/")
        return_url = f"{base_url}/static/stripe_success.html"
        refresh_url = f"{base_url}/static/stripe_cancel.html"
        
        onboarding_link = stripe_connect_service.create_account_link(
            stripe_account_id=result["stripe_account_id"],
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding"
        )
        
        logger.info(f"Created Express account {result['stripe_account_id']} for driver {driver_id}")
        
        return {
            "success": True,
            "message": "Express account created. Complete onboarding to activate.",
            "stripe_account_id": result["stripe_account_id"],
            "onboarding_url": onboarding_link.url,
            "account_type": "express"
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create Express account for driver {driver_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create Express account: {str(e)}"
        )



@router.post("/setup", response_model=StripeSetupResponse)
async def setup_stripe_account(
    request: StripeSetupRequest,
    http_request: Request,
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Stripe Custom Connected Account for the driver.
    
    This endpoint:
    1. Creates a Stripe Custom Account
    2. Attaches driver's bank account
    3. Submits KYC information
    4. Updates driver record with stripe_account_id
    
    The driver does NOT need to interact with Stripe - everything is automatic.
    """
    driver_id = current_driver.id
    
    # Check if driver already has a Stripe account
    if current_driver.stripe_account_id:
        # Return existing account status
        try:
            status = stripe_connect_service.get_account_status(
                current_driver.stripe_account_id
            )
            return StripeSetupResponse(
                success=True,
                message="Stripe account already exists",
                stripe_account_id=current_driver.stripe_account_id,
                verification_status=status.get("verification_status", "unknown"),
                payouts_enabled=status.get("payouts_enabled", False)
            )
        except Exception as e:
            logger.error(f"Error getting existing Stripe status: {e}")
            # Continue to create new account if existing one has issues
    
    # Get or create driver's bank details
    bank_result = await db.execute(
        select(DriverBankDetail).where(DriverBankDetail.driver_id == driver_id)
    )
    bank_detail = bank_result.scalar_one_or_none()
    
    if not bank_detail:
        # Create bank detail from request
        bank_detail = DriverBankDetail(
            driver_id=driver_id,
            bank_account_number=request.account_number,
            bank_ifsc=request.sort_code,
            account_holder_name=request.account_holder_name
        )
        db.add(bank_detail)
        await db.flush()
    else:
        # Update existing
        bank_detail.bank_account_number = request.account_number
        bank_detail.bank_ifsc = request.sort_code
        bank_detail.account_holder_name = request.account_holder_name
    
    # Update driver DOB and address if provided
    if request.dob:
        from datetime import datetime
        try:
            current_driver.dob = datetime.strptime(request.dob, "%Y-%m-%d")
        except ValueError:
            pass
    
    if request.address:
        current_driver.address = request.address
    
    # Get driver's documents for KYC
    doc_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_id == driver_id)
    )
    driver_doc = doc_result.scalar_one_or_none()
    
    # Get client IP address
    ip_address = request.ip_address
    if not ip_address:
        ip_address = http_request.client.host if http_request.client else "127.0.0.1"
    
    try:
        # Create Stripe Custom Account
        result = stripe_connect_service.create_custom_account(
            driver=current_driver,
            bank_detail=bank_detail,
            document=driver_doc,
            country=request.country,
            ip_address=ip_address
        )
        
        # Update driver record
        current_driver.stripe_account_id = result["stripe_account_id"]
        current_driver.stripe_verification_status = result.get("status", "pending")
        current_driver.stripe_payouts_enabled = result.get("payouts_enabled", False)
        current_driver.stripe_requirements_due = bool(result.get("requirements", {}).get("currently_due"))
        
        # Store last 4 digits of bank account for display
        if bank_detail.bank_account_number:
            current_driver.stripe_bank_last4 = bank_detail.bank_account_number[-4:]
        
        await db.commit()
        
        logger.info(f"Created Stripe account {result['stripe_account_id']} for driver {driver_id}")
        
        return StripeSetupResponse(
            success=True,
            message="Stripe account created successfully. Verification in progress.",
            stripe_account_id=result["stripe_account_id"],
            verification_status=result.get("status", "pending"),
            payouts_enabled=result.get("payouts_enabled", False)
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create Stripe account for driver {driver_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create payment account: {str(e)}"
        )


@router.get("/status")
async def get_stripe_status(
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current status of driver's Stripe Connected Account.
    
    Returns:
    - connected: Whether account exists
    - payouts_enabled: Can receive payouts
    - verification_status: pending/verified/failed
    - requirements: Any pending requirements from Stripe
    """
    if not current_driver.stripe_account_id:
        return {
            "connected": False,
            "message": "No Stripe account linked. Call POST /driver/stripe/setup to create one.",
            "verification_status": "not_connected",
            "payouts_enabled": False
        }
    
    try:
        status = stripe_connect_service.get_account_status(
            current_driver.stripe_account_id
        )
        
        # Update local status if changed
        if status.get("payouts_enabled") != current_driver.stripe_payouts_enabled:
            current_driver.stripe_payouts_enabled = status.get("payouts_enabled", False)
            current_driver.stripe_verification_status = status.get("verification_status", "pending")
            current_driver.stripe_requirements_due = bool(status.get("requirements", {}).get("currently_due"))
            await db.commit()
        
        return {
            "connected": True,
            "stripe_account_id": current_driver.stripe_account_id,
            "verification_status": status.get("verification_status", "unknown"),
            "payouts_enabled": status.get("payouts_enabled", False),
            "charges_enabled": status.get("charges_enabled", False),
            "details_submitted": status.get("details_submitted", False),
            "requirements": status.get("requirements", []),
            "bank_last4": current_driver.stripe_bank_last4,
            "currency": "EUR"
        }
        
    except Exception as e:
        logger.error(f"Error getting Stripe status: {e}")
        return {
            "connected": True,
            "stripe_account_id": current_driver.stripe_account_id,
            "verification_status": current_driver.stripe_verification_status or "unknown",
            "payouts_enabled": current_driver.stripe_payouts_enabled or False,
            "error": str(e)
        }


@router.get("/onboarding-link")
async def get_onboarding_link(
    http_request: Request,
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Get or regenerate the onboarding link for Express accounts.
    Use this if the driver hasn't completed onboarding yet.
    """
    if not current_driver.stripe_account_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe account linked. Create one first with /setup-express"
        )
    
    try:
        # Check current status
        status = stripe_connect_service.get_account_status(
            current_driver.stripe_account_id
        )
        
        if status.get("payouts_enabled"):
            return {
                "message": "Account is already fully onboarded and payouts are enabled",
                "payouts_enabled": True,
                "no_action_needed": True
            }
        
        # Generate new onboarding link
        base_url = str(http_request.base_url).rstrip("/")
        return_url = f"{base_url}/static/stripe_success.html"
        refresh_url = f"{base_url}/static/stripe_cancel.html"
        
        link = stripe_connect_service.create_account_link(
            stripe_account_id=current_driver.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding"
        )
        
        return {
            "onboarding_url": link.url,
            "message": "Complete onboarding to enable payouts",
            "payouts_enabled": False,
            "requirements": status.get("requirements", {})
        }
        
    except Exception as e:
        logger.error(f"Error creating onboarding link: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create onboarding link: {str(e)}"
        )



@router.get("/dashboard-link")
async def get_dashboard_link(
    http_request: Request,
    current_driver: Driver = Depends(get_current_driver_any_status)
):
    """
    Get a dashboard/management link for the driver's Stripe account.
    
    - For Express accounts: Returns Express Dashboard login link
    - For Custom accounts: Returns Account Update link (to manage bank details)
    """
    if not current_driver.stripe_account_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe account linked."
        )
    
    try:
        # 1. Try Express Dashboard Login Link
        link_data = stripe_connect_service.create_login_link(
            current_driver.stripe_account_id
        )
        return {
            "url": link_data["url"],
            "link_type": "express_dashboard",
            "description": "Full Stripe Express Dashboard - view earnings, payouts, and manage account"
        }
    except Exception:
        # 2. Fallback for Custom Accounts: Account Update Link
        try:
            base_url = str(http_request.base_url).rstrip("/")
            return_url = f"{base_url}/static/stripe_success.html"
            refresh_url = f"{base_url}/static/stripe_cancel.html"
            
            link = stripe_connect_service.create_account_link(
                stripe_account_id=current_driver.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_update"
            )
            return {
                "url": link.url,
                "link_type": "account_update",
                "description": "Account update link - manage bank details and identity verification"
            }
        except Exception as e2:
            logger.error(f"Error creating dashboard/update link: {e2}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create dashboard link: {str(e2)}"
            )


@router.post("/update-bank")
async def update_bank_account(
    request: BankUpdateRequest,
    current_driver: Driver = Depends(get_current_driver_any_status),
    db: AsyncSession = Depends(get_db)
):
    """
    Update driver's bank account details.
    
    This will:
    1. Update bank details in database
    2. Update bank account in Stripe (if connected)
    """
    driver_id = current_driver.id
    
    # Update in database
    bank_result = await db.execute(
        select(DriverBankDetail).where(DriverBankDetail.driver_id == driver_id)
    )
    bank_detail = bank_result.scalar_one_or_none()
    
    if not bank_detail:
        # Create new bank detail record
        bank_detail = DriverBankDetail(
            driver_id=driver_id,
            bank_account_number=request.account_number,
            bank_ifsc=request.sort_code,
            account_holder_name=request.account_holder_name
        )
        db.add(bank_detail)
    else:
        # Update existing
        bank_detail.bank_account_number = request.account_number
        bank_detail.bank_ifsc = request.sort_code
        bank_detail.account_holder_name = request.account_holder_name
    
    # Update Stripe if connected
    stripe_updated = False
    if current_driver.stripe_account_id:
        try:
            stripe_connect_service.attach_bank_account(
                stripe_account_id=current_driver.stripe_account_id,
                bank_detail=bank_detail,
                account_holder_name=request.account_holder_name,
                country="IE"  # EUR country
            )
            stripe_updated = True
            current_driver.stripe_bank_last4 = request.account_number[-4:]
        except Exception as e:
            logger.error(f"Failed to update Stripe bank account: {e}")
            # Continue - at least save to DB
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Bank account updated successfully",
        "stripe_updated": stripe_updated,
        "bank_last4": request.account_number[-4:]
    }


@router.get("/balance")
async def get_stripe_balance(
    current_driver: Driver = Depends(get_current_driver)
):
    """
    Get the balance in driver's Stripe Connected Account.
    
    Note: This is the Stripe balance, not the wallet balance.
    Money is transferred here before being paid out to bank.
    """
    if not current_driver.stripe_account_id:
        return {
            "available": 0,
            "pending": 0,
            "currency": "EUR",
            "message": "No Stripe account linked"
        }
    
    try:
        balance = stripe_connect_service.get_balance(
            current_driver.stripe_account_id
        )
        return balance
    except Exception as e:
        logger.error(f"Error getting Stripe balance: {e}")
        return {
            "available": 0,
            "pending": 0,
            "currency": "EUR",
            "error": str(e)
        }
