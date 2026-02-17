"""
Driver Wallet API Endpoints

Provides:
- GET /driver/wallet - Get wallet balance and transactions
- POST /driver/wallet/withdraw - Request withdrawal to bank
- GET /driver/wallet/transactions - Get transaction history
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.database import get_db
from core.dependencies import get_current_driver
from core.models import Driver, DriverWalletTransaction, DriverEarning, WalletTransactionType, Payment
from core.services.stripe_connect import stripe_connect_service
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/driver/wallet", tags=["Driver Wallet"])


class WalletSummary(BaseModel):
    """Wallet balance summary"""
    available_balance: float = Field(..., description="Available balance for withdrawal")
    pending_balance: float = Field(..., description="Pending earnings not yet available")
    total_earnings: float = Field(..., description="Total lifetime earnings")
    total_withdrawn: float = Field(..., description="Total amount withdrawn")
    currency: str = "EUR"
    stripe_payouts_enabled: bool = False


class WalletTransaction(BaseModel):
    """Transaction record"""
    id: str
    transaction_type: str
    amount: float
    description: Optional[str]
    status: str
    created_at: datetime
    issue_id: Optional[str] = None


class WithdrawRequest(BaseModel):
    """Withdrawal request payload"""
    amount: float = Field(..., gt=0, description="Amount to withdraw in EUR")


class WithdrawResponse(BaseModel):
    """Withdrawal response"""
    success: bool
    message: str
    transaction_id: Optional[str] = None
    amount: float
    status: str


@router.get("/", response_model=WalletSummary)
async def get_wallet_summary(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver's wallet summary including:
    - Available balance (can withdraw)
    - Pending balance (processing)
    - Total earnings
    - Total withdrawn
    """
    driver_id = current_driver.id
    
    # Calculate totals from wallet transactions
    # Earnings + Bonuses + Refunds
    earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["earning", "bonus", "refund"]),
            DriverWalletTransaction.status == "completed"
        )
    )
    total_earnings = float(earnings_result.scalar() or 0)
    
    # Withdrawals + Deductions
    withdrawals_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["withdrawal", "deduction"]),
            DriverWalletTransaction.status == "completed"
        )
    )
    total_withdrawn = float(withdrawals_result.scalar() or 0)
    
    # Pending withdrawals
    pending_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type == "withdrawal",
            DriverWalletTransaction.status == "pending"
        )
    )
    pending_withdrawals = float(pending_result.scalar() or 0)
    
    # Available balance = earnings - withdrawals - pending
    available_balance = total_earnings - total_withdrawn - pending_withdrawals
    
    return WalletSummary(
        available_balance=max(0, available_balance),
        pending_balance=pending_withdrawals,
        total_earnings=total_earnings,
        total_withdrawn=total_withdrawn,
        currency="EUR",
        stripe_payouts_enabled=current_driver.stripe_payouts_enabled or False
    )


@router.get("/transactions", response_model=List[WalletTransaction])
async def get_wallet_transactions(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    transaction_type: Optional[str] = Query(None, description="Filter by type: earning, withdrawal, etc.")
):
    """Get driver's wallet transaction history"""
    query = select(DriverWalletTransaction).where(
        DriverWalletTransaction.driver_id == current_driver.id
    ).order_by(DriverWalletTransaction.created_at.desc())
    
    if transaction_type:
        query = query.where(DriverWalletTransaction.transaction_type == transaction_type)
    
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    return [
        WalletTransaction(
            id=str(t.id),
            transaction_type=t.transaction_type,
            amount=float(t.amount),
            description=t.description,
            status=t.status,
            created_at=t.created_at,
            issue_id=str(t.issue_id) if t.issue_id else None
        )
        for t in transactions
    ]


@router.post("/withdraw", response_model=WithdrawResponse)
async def request_withdrawal(
    request: WithdrawRequest,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Request withdrawal of available balance to driver's bank account.
    
    Flow:
    1. Check available balance in DB
    2. Check driver's Stripe account is payout-enabled
    3. Create Transfer from Platform to Driver's Stripe account
    4. Stripe automatically pays out to driver's bank (or we trigger payout)
    5. Record transaction in DB and Payment table
    """
    amount = request.amount
    driver_id = current_driver.id
    
    # Check if driver has Stripe account
    if not current_driver.stripe_account_id:
        raise HTTPException(
            status_code=400,
            detail="No payment account linked. Please complete bank account setup."
        )
    
    # Check if payouts are enabled
    if not current_driver.stripe_payouts_enabled:
        raise HTTPException(
            status_code=400,
            detail="Payment account not verified. Please wait for verification or contact support."
        )
    
    # Calculate available balance
    earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["earning", "bonus", "refund"]),
            DriverWalletTransaction.status == "completed"
        )
    )
    total_earnings = float(earnings_result.scalar() or 0)
    
    withdrawals_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["withdrawal", "deduction"]),
            DriverWalletTransaction.status.in_(["completed", "pending"])
        )
    )
    total_withdrawn = float(withdrawals_result.scalar() or 0)
    
    available_balance = total_earnings - total_withdrawn
    
    if amount > available_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: €{available_balance:.2f}"
        )
    
    # Minimum withdrawal amount
    if amount < 1.0:
        raise HTTPException(
            status_code=400,
            detail="Minimum withdrawal amount is €1.00"
        )
    
    try:
        # Create withdrawal transaction (pending)
        withdrawal_transaction = DriverWalletTransaction(
            driver_id=driver_id,
            transaction_type="withdrawal",
            amount=Decimal(str(amount)),
            currency="EUR",
            description=f"Withdrawal to bank account",
            status="pending"
        )
        db.add(withdrawal_transaction)
        await db.flush()  # Get the ID
        
        # Create transfer from platform to driver's Stripe account
        amount_in_cents = int(amount * 100)  # EUR uses cents
        transfer_result = stripe_connect_service.create_transfer(
            stripe_account_id=current_driver.stripe_account_id,
            amount_in_cents=amount_in_cents,
            currency="eur",
            description=f"Withdrawal - Driver {str(driver_id)[:8]}",
            metadata={
                "driver_id": str(driver_id),
                "transaction_id": str(withdrawal_transaction.id)
            }
        )
        
        # Update transaction with transfer ID
        withdrawal_transaction.stripe_transfer_id = transfer_result["transfer_id"]
        withdrawal_transaction.status = "completed"  # Transfer is instant
        
        # Also record in Payment table for the admin view
        payment_record = Payment(
            driver_id=driver_id,
            payment_type="driver_withdrawal",
            amount=Decimal(str(amount)),
            currency="EUR",
            stripe_transfer_id=transfer_result["transfer_id"],
            status="completed",
            description=f"Withdrawal of €{amount:.2f} to bank account"
        )
        db.add(payment_record)
        
        await db.commit()
        
        logger.info(f"Withdrawal successful: €{amount} for driver {driver_id}")
        
        return WithdrawResponse(
            success=True,
            message=f"Withdrawal of €{amount:.2f} initiated. Funds will arrive in your bank within 2-3 business days.",
            transaction_id=str(withdrawal_transaction.id),
            amount=amount,
            status="completed"
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Withdrawal failed for driver {driver_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Withdrawal failed: {str(e)}"
        )


@router.get("/stripe-status")
async def get_stripe_account_status(
    current_driver: Driver = Depends(get_current_driver)
):
    """Get the status of driver's Stripe connected account"""
    if not current_driver.stripe_account_id:
        return {
            "connected": False,
            "message": "No Stripe account linked"
        }
    
    try:
        status = stripe_connect_service.get_account_status(
            current_driver.stripe_account_id
        )
        return {
            "connected": True,
            **status
        }
    except Exception as e:
        logger.error(f"Error getting Stripe status: {e}")
        return {
            "connected": True,
            "stripe_account_id": current_driver.stripe_account_id,
            "error": str(e)
        }
