"""
Admin Platform API - Platform balance and fee management
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import stripe
import uuid

from core.database import get_db
from core.models import Payment, DriverEarning
from core.dependencies import get_current_admin  # Assuming this exists
from config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/platform", tags=["Admin Platform"])

stripe.api_key = settings.STRIPE_SECRET_KEY


class PlatformBalanceResponse(BaseModel):
    """Platform balance summary"""
    total_platform_earnings: float  # Total platform fees collected
    stripe_available_balance: float  # Available in Stripe
    stripe_pending_balance: float  # Pending in Stripe
    total_jobs_processed: int
    currency: str


class PlatformEarningResponse(BaseModel):
    """Platform earning record"""
    id: str
    issue_id: str
    driver_id: str
    platform_fee: float
    total_job_amount: float
    date: datetime
    status: str


class TransferRequest(BaseModel):
    """Request to transfer platform balance to company bank"""
    amount: float
    description: Optional[str] = "Platform fee transfer to company account"


@router.get("/balance", response_model=PlatformBalanceResponse)
async def get_platform_balance(
    db: AsyncSession = Depends(get_db)
):
    """
    Get platform balance and earnings summary
    Shows total platform fees and Stripe balance
    """
    try:
        # Get total platform fees from DB
        platform_fees_result = await db.execute(
            select(func.sum(Payment.platform_fee)).where(
                Payment.payment_type == "customer_payment",
                Payment.status == "completed",
                Payment.platform_fee.isnot(None)
            )
        )
        total_platform_earnings = platform_fees_result.scalar() or Decimal("0.00")
        
        # Get total jobs processed
        jobs_result = await db.execute(
            select(func.count(Payment.id)).where(
                Payment.payment_type == "customer_payment",
                Payment.status == "completed"
            )
        )
        total_jobs = jobs_result.scalar() or 0
        
        # Get Stripe balance
        stripe_balance = stripe.Balance.retrieve()
        
        available_balance = 0.0
        pending_balance = 0.0
        
        if stripe_balance.available:
            # Convert from pence to pounds
            available_balance = stripe_balance.available[0].amount / 100.0
        
        if stripe_balance.pending:
            pending_balance = stripe_balance.pending[0].amount / 100.0
        
        return PlatformBalanceResponse(
            total_platform_earnings=float(total_platform_earnings),
            stripe_available_balance=available_balance,
            stripe_pending_balance=pending_balance,
            total_jobs_processed=total_jobs,
            currency="GBP"
        )
        
    except Exception as e:
        logger.error(f"Error fetching platform balance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch platform balance: {str(e)}")


@router.get("/earnings", response_model=List[PlatformEarningResponse])
async def get_platform_earnings(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed platform earnings history
    Shows all platform fees collected
    """
    result = await db.execute(
        select(Payment)
        .where(
            Payment.payment_type == "platform_fee",
            Payment.status == "completed"
        )
        .order_by(desc(Payment.created_at))
        .offset(skip)
        .limit(limit)
    )
    payments = result.scalars().all()
    
    return [
        PlatformEarningResponse(
            id=str(payment.id),
            issue_id=str(payment.issue_id),
            driver_id=str(payment.driver_id),
            platform_fee=float(payment.amount),
            total_job_amount=float(payment.total_amount or payment.amount),
            date=payment.created_at,
            status=payment.status
        )
        for payment in payments
    ]


@router.post("/transfer")
async def transfer_platform_balance(
    transfer_request: TransferRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Transfer platform balance from Stripe to company bank account
    Creates a Stripe payout to the company's bank account
    """
    try:
        # Validate amount
        if transfer_request.amount <= 0:
            raise HTTPException(status_code=400, detail="Transfer amount must be positive")
        
        # Check Stripe available balance
        stripe_balance = stripe.Balance.retrieve()
        available_balance = 0.0
        
        if stripe_balance.available:
            available_balance = stripe_balance.available[0].amount / 100.0
        
        if transfer_request.amount > available_balance:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient balance. Available: £{available_balance:.2f}"
            )
        
        # Create Stripe payout (transfer to company bank account)
        # Note: This requires Stripe account to have a bank account configured
        payout = stripe.Payout.create(
            amount=int(transfer_request.amount * 100),  # Convert to pence
            currency="gbp",
            description=transfer_request.description,
            metadata={
                "type": "platform_fee_transfer",
                "requested_by": "admin"
            }
        )
        
        # Record the transfer in our database
        transfer_payment = Payment(
            id=uuid.uuid4(),
            payment_type="platform_transfer",
            amount=Decimal(str(transfer_request.amount)),
            currency="GBP",
            stripe_payout_id=payout.id,
            status="processing",
            description=transfer_request.description
        )
        
        db.add(transfer_payment)
        await db.commit()
        await db.refresh(transfer_payment)
        
        logger.info(f"Platform transfer initiated: £{transfer_request.amount} - Payout ID: {payout.id}")
        
        return {
            "success": True,
            "transfer_id": str(transfer_payment.id),
            "stripe_payout_id": payout.id,
            "amount": transfer_request.amount,
            "currency": "GBP",
            "status": "processing",
            "estimated_arrival": payout.arrival_date
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during transfer: {e}")
        raise HTTPException(status_code=500, detail=f"Transfer failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error during platform transfer: {e}")
        raise HTTPException(status_code=500, detail=f"Transfer failed: {str(e)}")


@router.get("/transfers")
async def get_transfer_history(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Get history of platform balance transfers to company bank
    """
    result = await db.execute(
        select(Payment)
        .where(Payment.payment_type == "platform_transfer")
        .order_by(desc(Payment.created_at))
        .offset(skip)
        .limit(limit)
    )
    transfers = result.scalars().all()
    
    return [
        {
            "id": str(transfer.id),
            "amount": float(transfer.amount),
            "currency": transfer.currency,
            "status": transfer.status,
            "stripe_payout_id": transfer.stripe_payout_id,
            "description": transfer.description,
            "created_at": transfer.created_at,
            "updated_at": transfer.updated_at
        }
        for transfer in transfers
    ]