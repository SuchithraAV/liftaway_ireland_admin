"""
Payment Processing API - Handles payment creation and processing with commission split
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
import uuid
import stripe
import logging

from core.database import get_db
from core.models import Issue, Customer, Driver
from core.services.stripe_payment_service import StripePaymentService
from core.dependencies import get_current_customer  # Assuming this exists
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment", tags=["Payment Processing"])

stripe.api_key = settings.STRIPE_SECRET_KEY


class CreatePaymentRequest(BaseModel):
    """Request to create payment for an issue"""
    issue_id: str
    total_amount: float  # Total job cost (e.g., 100.00 GBP)


class PaymentResponse(BaseModel):
    """Payment creation response"""
    payment_id: str
    payment_intent_id: str
    client_secret: str
    total_amount: float
    currency: str
    # Note: driver_amount and platform_fee are NOT exposed to customer


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    payment_request: CreatePaymentRequest,
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db)
):
    """
    Create payment for an issue with automatic commission split
    Customer sees FULL amount, split is handled internally
    """
    try:
        # Validate issue
        issue_uuid = uuid.UUID(payment_request.issue_id)
        result = await db.execute(
            select(Issue).where(Issue.id == issue_uuid)
        )
        issue = result.scalar_one_or_none()
        
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        if issue.customer_id != current_customer.id:
            raise HTTPException(status_code=403, detail="Not authorized for this issue")
        
        if not issue.assigned_driver_id:
            raise HTTPException(status_code=400, detail="No driver assigned to this issue")
        
        # Validate amount
        total_amount = Decimal(str(payment_request.total_amount))
        if total_amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Create payment with split using our service
        idempotency_key = f"payment_{issue_uuid}_{current_customer.id}"
        
        payment_result = await StripePaymentService.create_payment_intent_with_split(
            issue_id=issue_uuid,
            total_amount=total_amount,
            customer_id=current_customer.id,
            driver_id=issue.assigned_driver_id,
            db=db,
            idempotency_key=idempotency_key
        )
        
        # Return response WITHOUT exposing split details to customer
        return PaymentResponse(
            payment_id=payment_result["payment_id"],
            payment_intent_id=payment_result["payment_intent_id"],
            client_secret=payment_result["client_secret"],
            total_amount=payment_result["total_amount"],
            currency=payment_result["currency"]
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment")


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe webhook events for payment processing
    Processes successful payments and updates driver earnings
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("Invalid payload in webhook")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid signature in webhook")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle payment success
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        payment_intent_id = payment_intent['id']
        
        try:
            await StripePaymentService.process_successful_payment(
                payment_intent_id=payment_intent_id,
                db=db
            )
            logger.info(f"Successfully processed payment: {payment_intent_id}")
        except Exception as e:
            logger.error(f"Error processing successful payment {payment_intent_id}: {e}")
            # Don't raise exception to avoid webhook retry
    
    # Handle payment failure
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        payment_intent_id = payment_intent['id']
        
        # Update payment status to failed
        from core.models import Payment
        result = await db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
        )
        payment = result.scalar_one_or_none()
        
        if payment:
            payment.status = "failed"
            payment.failure_reason = payment_intent.get('last_payment_error', {}).get('message', 'Payment failed')
            await db.commit()
            logger.info(f"Payment failed: {payment_intent_id}")
    
    return {"status": "success"}


@router.get("/status/{payment_id}")
async def get_payment_status(
    payment_id: str,
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db)
):
    """
    Get payment status for customer
    Does NOT expose commission split details
    """
    try:
        payment_uuid = uuid.UUID(payment_id)
        
        from core.models import Payment
        result = await db.execute(
            select(Payment).where(Payment.id == payment_uuid)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        if payment.customer_id != current_customer.id:
            raise HTTPException(status_code=403, detail="Not authorized for this payment")
        
        return {
            "payment_id": str(payment.id),
            "status": payment.status,
            "amount": float(payment.amount),  # Total amount only
            "currency": payment.currency,
            "created_at": payment.created_at,
            "updated_at": payment.updated_at
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment ID")