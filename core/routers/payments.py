"""
Payments Router - Endpoints for payment processing and history

This router provides APIs for:
- Creating payment orders (Razorpay/Stripe)
- Verifying payments
- Listing all payments (admin view)
- Driver-specific payments
- Withdrawal history
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime
import uuid as uuid_module

from config import settings
from core.database import get_db
from core.models import Payment, Driver, Customer, Issue
from core.dependencies import get_current_driver
from core.utils.field_encryption import decrypt_field


router = APIRouter(prefix="/payments", tags=["Payments"])


# ============== Pydantic Schemas ==============

class PaymentResponse(BaseModel):
    id: str
    customer_id: Optional[str]
    driver_id: Optional[str]
    issue_id: Optional[str]
    payment_type: str
    amount: float
    currency: str
    status: str
    description: Optional[str]
    stripe_payment_intent_id: Optional[str]
    stripe_transfer_id: Optional[str]
    stripe_payout_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    # Resolved names
    customer_name: Optional[str] = None
    driver_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    total: int
    payments: List[PaymentResponse]


# ============== Payment History Endpoints ==============

@router.get("/all", response_model=List[PaymentResponse])
async def get_all_payments(
    skip: int = 0,
    limit: int = 100,
    payment_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    driver_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all payments with optional filters (Admin endpoint)
    
    Query Parameters:
    - skip: Number of records to skip (pagination)
    - limit: Max records to return
    - payment_type: Filter by type (customer_payment, driver_earning, driver_withdrawal, platform_fee)
    - status_filter: Filter by status (pending, completed, failed)
    - driver_id: Filter by specific driver
    """
    query = select(Payment).options(
        selectinload(Payment.customer),
        selectinload(Payment.driver)
    )
    
    # Apply filters
    if payment_type:
        query = query.where(Payment.payment_type == payment_type)
    if status_filter:
        query = query.where(Payment.status == status_filter)
    if driver_id:
        query = query.where(Payment.driver_id == driver_id)
    
    # Order by most recent first
    query = query.order_by(desc(Payment.created_at))
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    payments = result.scalars().all()
    
    # Build response with resolved names
    response_list = []
    for payment in payments:
        response = PaymentResponse(
            id=str(payment.id),
            customer_id=str(payment.customer_id) if payment.customer_id else None,
            driver_id=str(payment.driver_id) if payment.driver_id else None,
            issue_id=str(payment.issue_id) if payment.issue_id else None,
            payment_type=payment.payment_type,
            amount=float(payment.amount),
            currency=payment.currency or "EUR",
            status=payment.status,
            description=payment.description,
            stripe_payment_intent_id=payment.stripe_payment_intent_id,
            stripe_transfer_id=payment.stripe_transfer_id,
            stripe_payout_id=payment.stripe_payout_id,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            customer_name=decrypt_field(payment.customer.full_name) if payment.customer and payment.customer.full_name else None,
            driver_name=decrypt_field(payment.driver.full_name) if payment.driver and payment.driver.full_name else None
        )
        response_list.append(response)
    
    return response_list


@router.get("/driver/me", response_model=List[PaymentResponse])
async def get_my_payments(
    skip: int = 0,
    limit: int = 50,
    payment_type: Optional[str] = None,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all payments for the authenticated driver
    """
    query = select(Payment).options(
        selectinload(Payment.customer)
    ).where(Payment.driver_id == current_driver.id)
    
    if payment_type:
        query = query.where(Payment.payment_type == payment_type)
    
    query = query.order_by(desc(Payment.created_at))
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    payments = result.scalars().all()
    
    response_list = []
    for payment in payments:
        response = PaymentResponse(
            id=str(payment.id),
            customer_id=str(payment.customer_id) if payment.customer_id else None,
            driver_id=str(payment.driver_id) if payment.driver_id else None,
            issue_id=str(payment.issue_id) if payment.issue_id else None,
            payment_type=payment.payment_type,
            amount=float(payment.amount),
            currency=payment.currency or "EUR",
            status=payment.status,
            description=payment.description,
            stripe_payment_intent_id=payment.stripe_payment_intent_id,
            stripe_transfer_id=payment.stripe_transfer_id,
            stripe_payout_id=payment.stripe_payout_id,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            customer_name=decrypt_field(payment.customer.full_name) if payment.customer and payment.customer.full_name else None,
            driver_name=decrypt_field(current_driver.full_name) if current_driver.full_name else None
        )
        response_list.append(response)
    
    return response_list


@router.get("/withdrawals", response_model=List[PaymentResponse])
async def get_all_withdrawals(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all driver withdrawals (Admin endpoint for Payments Table view)
    
    Returns driver_id, withdrawn_amount, date, and status for all withdrawal payments
    """
    query = select(Payment).options(
        selectinload(Payment.driver)
    ).where(Payment.payment_type == "driver_withdrawal")
    
    if status_filter:
        query = query.where(Payment.status == status_filter)
    
    query = query.order_by(desc(Payment.created_at))
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    payments = result.scalars().all()
    
    response_list = []
    for payment in payments:
        response = PaymentResponse(
            id=str(payment.id),
            customer_id=str(payment.customer_id) if payment.customer_id else None,
            driver_id=str(payment.driver_id) if payment.driver_id else None,
            issue_id=str(payment.issue_id) if payment.issue_id else None,
            payment_type=payment.payment_type,
            amount=float(payment.amount),
            currency=payment.currency or "EUR",
            status=payment.status,
            description=payment.description,
            stripe_payment_intent_id=payment.stripe_payment_intent_id,
            stripe_transfer_id=payment.stripe_transfer_id,
            stripe_payout_id=payment.stripe_payout_id,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            customer_name=decrypt_field(payment.customer.full_name) if payment.customer and payment.customer.full_name else None,
            driver_name=decrypt_field(payment.driver.full_name) if payment.driver and payment.driver.full_name else None
        )
        response_list.append(response)
    
    return response_list


@router.get("/summary")
async def get_payments_summary(db: AsyncSession = Depends(get_db)):
    """
    Get summary statistics for all payments
    """
    # Total customer payments
    customer_result = await db.execute(
        select(func.sum(Payment.amount)).where(
            Payment.payment_type == "customer_payment",
            Payment.status == "completed"
        )
    )
    customer_payments = customer_result.scalar() or 0
    
    # Total driver earnings
    earnings_result = await db.execute(
        select(func.sum(Payment.amount)).where(
            Payment.payment_type == "driver_earning",
            Payment.status == "completed"
        )
    )
    driver_earnings = earnings_result.scalar() or 0
    
    # Total withdrawals
    withdrawals_result = await db.execute(
        select(func.sum(Payment.amount)).where(
            Payment.payment_type == "driver_withdrawal",
            Payment.status == "completed"
        )
    )
    total_withdrawals = withdrawals_result.scalar() or 0
    
    # Total platform fees
    fees_result = await db.execute(
        select(func.sum(Payment.amount)).where(
            Payment.payment_type == "platform_fee",
            Payment.status == "completed"
        )
    )
    platform_fees = fees_result.scalar() or 0
    
    # Counts
    total_result = await db.execute(select(func.count(Payment.id)))
    total_payments = total_result.scalar() or 0
    
    pending_result = await db.execute(
        select(func.count(Payment.id)).where(Payment.status == "pending")
    )
    pending_payments = pending_result.scalar() or 0
    
    return {
        "currency": "EUR",
        "total_customer_payments": float(customer_payments),
        "total_driver_earnings": float(driver_earnings),
        "total_withdrawals": float(total_withdrawals),
        "total_platform_fees": float(platform_fees),
        "total_payment_count": total_payments,
        "pending_payment_count": pending_payments
    }


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment_detail(
    payment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific payment
    """
    try:
        payment_uuid = uuid_module.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")
    
    result = await db.execute(
        select(Payment).options(
            selectinload(Payment.customer),
            selectinload(Payment.driver)
        ).where(Payment.id == payment_uuid)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return PaymentResponse(
        id=str(payment.id),
        customer_id=str(payment.customer_id) if payment.customer_id else None,
        driver_id=str(payment.driver_id) if payment.driver_id else None,
        issue_id=str(payment.issue_id) if payment.issue_id else None,
        payment_type=payment.payment_type,
        amount=float(payment.amount),
        currency=payment.currency or "EUR",
        status=payment.status,
        description=payment.description,
        stripe_payment_intent_id=payment.stripe_payment_intent_id,
        stripe_transfer_id=payment.stripe_transfer_id,
        stripe_payout_id=payment.stripe_payout_id,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        customer_name=decrypt_field(payment.customer.full_name) if payment.customer and payment.customer.full_name else None,
        driver_name=decrypt_field(payment.driver.full_name) if payment.driver and payment.driver.full_name else None
    )
