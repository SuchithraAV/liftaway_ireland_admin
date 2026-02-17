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
from core.models import Driver, DriverWalletTransaction, DriverEarning, WalletTransactionType, Payment, DriverBankDetail, DriverWithdrawRequest
from core.services.stripe_connect import stripe_connect_service
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
import logging
import stripe
from config import settings
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# Set Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/driver", tags=["Driver Wallet"])


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


@router.get("/wallet", response_model=WalletSummary)
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
    
    # Calculate totals
    
    # 1. Job Earnings from DriverEarning table (Source of Truth for Jobs)
    job_earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverEarning.amount), 0)).where(
            DriverEarning.driver_id == driver_id
        )
    )
    job_earnings = float(job_earnings_result.scalar() or 0)

    # 2. Other Earnings (Bonuses, Refunds) from WalletTransactions
    other_earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["bonus", "refund"]),
            DriverWalletTransaction.status == "completed"
        )
    )
    other_earnings = float(other_earnings_result.scalar() or 0)
    
    total_earnings = job_earnings + other_earnings
    
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


@router.get("/wallet/transactions", response_model=List[WalletTransaction])
async def get_wallet_transactions(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    transaction_type: Optional[str] = Query(None, description="Filter by type: earning, withdrawal, etc.")
):
    """Get driver's wallet transaction history (async)"""
    stmt = select(DriverWalletTransaction).where(
        DriverWalletTransaction.driver_id == current_driver.id
    ).order_by(DriverWalletTransaction.created_at.desc())

    if transaction_type:
        stmt = stmt.where(DriverWalletTransaction.transaction_type == transaction_type)

    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
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
    Request withdrawal of available balance to driver's bank account (GBP version).
    """

    amount = request.amount
    driver_id = current_driver.id
    
    # Check payment method (Stripe or Bank Details)
    use_stripe = False
    bank_details = None
    
    if current_driver.stripe_account_id and current_driver.stripe_payouts_enabled:
        use_stripe = True
    else:
        bank_details_result = await db.execute(
            select(DriverBankDetail).where(DriverBankDetail.driver_id == driver_id)
        )
        bank_details = bank_details_result.scalar_one_or_none()
        
        if not bank_details:
            raise HTTPException(
                status_code=400,
                detail="No payment account linked. Please complete bank account setup."
            )
    
    # Calculate available balance (DB earnings logic unchanged)
    job_earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverEarning.amount), 0)).where(
            DriverEarning.driver_id == driver_id
        )
    )
    job_earnings = float(job_earnings_result.scalar() or 0)

    other_earnings_result = await db.execute(
        select(func.coalesce(func.sum(DriverWalletTransaction.amount), 0)).where(
            DriverWalletTransaction.driver_id == driver_id,
            DriverWalletTransaction.transaction_type.in_(["bonus", "refund"]),
            DriverWalletTransaction.status == "completed"
        )
    )
    other_earnings = float(other_earnings_result.scalar() or 0)
    
    total_earnings = job_earnings + other_earnings

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
            detail=f"Insufficient balance. Available: £{available_balance:.2f}"
        )
    
    # Minimum withdrawal amount
    if amount < 1.0:
        raise HTTPException(
            status_code=400,
            detail="Minimum withdrawal amount is £1.00"
        )
    
    # Check Stripe available balance BEFORE creating transfer
    stripe_balance = stripe.Balance.retrieve()

    stripe_available_gbp = 0
    for item in stripe_balance.available:
        if item.currency.lower() == "gbp":
            stripe_available_gbp = item.amount  # in pence

    amount_in_pence = int(amount * 100)

    if amount_in_pence > stripe_available_gbp:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient Stripe funds. Platform GBP available: £{stripe_available_gbp/100:.2f}, "
                f"requested: £{amount:.2f}. "
                "Add funds using test card 4000000000000077."
            )
        )

    try:
        # Create pending transaction
        withdrawal_transaction = DriverWalletTransaction(
            driver_id=driver_id,
            transaction_type="withdrawal",
            amount=Decimal(str(amount)),
            currency="GBP",
            description=f"Withdrawal to bank account",
            status="pending"
        )
        db.add(withdrawal_transaction)
        await db.flush()

        transfer_id = None
        
        if use_stripe:
            # Perform Stripe transfer (GBP)
            transfer_result = await run_in_threadpool(
                stripe_connect_service.create_transfer,
                current_driver.stripe_account_id,
                amount_in_pence,
                "gbp",   # ✔ FIX: USD/EUR removed, using GBP
                f"Withdrawal - Driver {str(driver_id)[:8]}",
                {
                    "driver_id": str(driver_id),
                    "transaction_id": str(withdrawal_transaction.id)
                }
            )

            transfer_id = transfer_result.get("transfer_id")
            withdrawal_transaction.stripe_transfer_id = transfer_id
            withdrawal_transaction.status = "completed"
            withdrawal_transaction.description = f"Stripe Withdrawal to {current_driver.stripe_account_id}"
        
        else:
            withdrawal_transaction.status = "completed"
            acc_num = bank_details.bank_account_number if bank_details else "Unknown"
            withdrawal_transaction.description = f"Bank Withdrawal to {acc_num}"

        # Record into Payment table
        payment_record = Payment(
            driver_id=driver_id,
            payment_type="driver_withdrawal",
            amount=Decimal(str(amount)),
            currency="GBP",
            stripe_transfer_id=transfer_id,
            status="completed",
            description=withdrawal_transaction.description
        )
        db.add(payment_record)

        # Create withdrawal history record
        withdraw_request = DriverWithdrawRequest(
            driver_id=driver_id,
            amount=Decimal(str(amount)),
            status="paid" if use_stripe else "requested",
            stripe_transfer_id=transfer_id
        )
        db.add(withdraw_request)

        await db.commit()

        return WithdrawResponse(
            success=True,
            message=f"Withdrawal of £{amount:.2f} initiated. Funds will arrive in your bank within 2–3 business days.",
            transaction_id=str(withdrawal_transaction.id),
            amount=amount,
            status="completed"
        )

    except Exception as e:
        await db.rollback()
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
        status = await run_in_threadpool(
            stripe_connect_service.get_account_status,
            current_driver.stripe_account_id
        )
        return {
            "connected": True,
            **(status or {})
        }
    except Exception as e:
        logger.error(f"Error getting Stripe status: {e}")
        return {
            "connected": True,
            "stripe_account_id": current_driver.stripe_account_id,
            "error": str(e)
        }


@router.post("/wallet/add-test-earnings")
async def add_test_earnings(
    amount: float,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    TEST ONLY: Add test earnings to driver wallet for testing withdrawals.
    Remove this endpoint in production!
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    # Add earning record
    earning = DriverEarning(
        driver_id=current_driver.id,
        date=datetime.utcnow(),
        jobs_done=1,
        amount=Decimal(str(amount)),
        payout_status="pending",
        available_for_payout=True
    )
    db.add(earning)
    
    # Add wallet transaction
    transaction = DriverWalletTransaction(
        driver_id=current_driver.id,
        transaction_type="earning",
        amount=Decimal(str(amount)),
        description=f"Test earning - €{amount}",
        status="completed"
    )
    db.add(transaction)
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Added €{amount} test earnings to wallet",
        "amount": amount
    }


@router.post("/wallet/test-customer-payment")
async def test_customer_payment(
    amount: float,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    TEST ONLY: Simulate a customer payment to create real Stripe balance.
    This creates a PaymentIntent and confirms it, adding funds to your platform account.
    """
    import stripe
    from config import settings
    
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    try:
        # Create a test PaymentIntent
        amount_cents = int(amount * 100)
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            payment_method_types=["card"],
            metadata={
                "driver_id": str(current_driver.id),
                "test_payment": "true"
            }
        )
        
        # Confirm it with test card that adds to available balance
        # Card 4000000000000077 bypasses the pending balance and goes straight to available
        confirmed = stripe.PaymentIntent.confirm(
            payment_intent.id,
            payment_method_data={
                "type": "card",
                "card": {
                    "number": "4000000000000077",
                    "exp_month": 12,
                    "exp_year": 2025,
                    "cvc": "123"
                }
            }
        )
        
        # Add earning record to driver
        earning = DriverEarning(
            driver_id=current_driver.id,
            date=datetime.utcnow(),
            jobs_done=1,
            amount=Decimal(str(amount)),
            payout_status="pending",
            available_for_payout=True
        )
        db.add(earning)
        
        # Add wallet transaction
        transaction = DriverWalletTransaction(
            driver_id=current_driver.id,
            transaction_type="earning",
            amount=Decimal(str(amount)),
            description=f"Test customer payment - €{amount}",
            status="completed",
            stripe_payment_intent_id=payment_intent.id
        )
        db.add(transaction)
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Simulated customer payment of €{amount}",
            "payment_intent_id": payment_intent.id,
            "status": confirmed.status,
            "amount": amount,
            "note": "This created real Stripe balance. Now you can withdraw!"
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Test payment failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Test payment failed: {str(e)}"
        )


