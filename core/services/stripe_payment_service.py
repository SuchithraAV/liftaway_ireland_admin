"""
Stripe Payment Service - Handles Stripe payment processing with commission split
"""

import stripe
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import uuid
import logging

from config import settings
from core.models import Payment, Issue, Driver, DriverEarning
from core.services.payment_split import PaymentSplitService
from core.redis_client import redis_pool

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripePaymentService:
    """Service to handle Stripe payment processing with platform commission"""
    
    @staticmethod
    async def create_payment_intent_with_split(
        issue_id: uuid.UUID,
        total_amount: Decimal,
        customer_id: uuid.UUID,
        driver_id: uuid.UUID,
        db: AsyncSession,
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Create Stripe PaymentIntent for full amount and store split in DB
        
        Args:
            issue_id: Issue/Job ID
            total_amount: Total job cost (e.g., 100 GBP)
            customer_id: Customer UUID
            driver_id: Driver UUID
            db: Database session
            idempotency_key: Stripe idempotency key for duplicate prevention
            
        Returns:
            Dict with payment_intent_id, client_secret, and split details
        """
        # Calculate split
        split = PaymentSplitService.calculate_split(total_amount)
        
        # Use Redis lock to prevent duplicate processing
        redis_client = redis_pool.get_client()
        lock_key = f"payment_lock:{issue_id}"
        
        try:
            # Try to acquire lock (expires in 30 seconds)
            lock_acquired = await redis_client.set(lock_key, "1", nx=True, ex=30)
            
            if not lock_acquired:
                raise ValueError("Payment already being processed for this issue")
            
            # Check if payment already exists
            existing = await db.execute(
                select(Payment).where(
                    Payment.issue_id == issue_id,
                    Payment.payment_type == "customer_payment"
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("Payment already exists for this issue")
            
            # Create Stripe PaymentIntent for FULL amount
            amount_in_pence = int(total_amount * 100)  # Convert to pence
            
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_in_pence,
                currency="gbp",
                metadata={
                    "issue_id": str(issue_id),
                    "customer_id": str(customer_id),
                    "driver_id": str(driver_id),
                    "driver_amount": str(split["driver_amount"]),
                    "platform_fee": str(split["platform_fee"])
                },
                idempotency_key=idempotency_key
            )
            
            # Store payment in DB with split details
            payment = Payment(
                id=uuid.uuid4(),
                customer_id=customer_id,
                driver_id=driver_id,
                issue_id=issue_id,
                payment_type="customer_payment",
                amount=total_amount,
                total_amount=total_amount,
                driver_amount=split["driver_amount"],
                platform_fee=split["platform_fee"],
                currency="GBP",
                stripe_payment_intent_id=payment_intent.id,
                status="pending",
                description=f"Job payment - Issue {issue_id}"
            )
            
            db.add(payment)
            await db.commit()
            await db.refresh(payment)
            
            logger.info(f"Payment intent created: {payment_intent.id} for issue {issue_id}")
            
            return {
                "payment_id": str(payment.id),
                "payment_intent_id": payment_intent.id,
                "client_secret": payment_intent.client_secret,
                "total_amount": float(total_amount),
                "driver_amount": float(split["driver_amount"]),
                "platform_fee": float(split["platform_fee"]),
                "currency": "GBP"
            }
            
        finally:
            # Release lock
            await redis_client.delete(lock_key)
            await redis_client.close()
    
    @staticmethod
    async def process_successful_payment(
        payment_intent_id: str,
        db: AsyncSession
    ) -> None:
        """
        Process successful payment - update status and create driver earning record
        
        Args:
            payment_intent_id: Stripe PaymentIntent ID
            db: Database session
        """
        # Find payment
        result = await db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise ValueError(f"Payment not found for intent {payment_intent_id}")
        
        # Update payment status
        payment.status = "completed"
        
        # Create driver earning record (driver's share only)
        driver_earning = DriverEarning(
            driver_id=payment.driver_id,
            issue_id=payment.issue_id,
            date=datetime.now(timezone.utc),
            jobs_done=1,
            amount=payment.driver_amount,  # Driver's 80% share
            total_job_amount=payment.total_amount,
            platform_fee=payment.platform_fee,
            payout_status="pending",
            available_for_payout=True
        )
        
        db.add(driver_earning)
        
        # Create platform fee record
        platform_payment = Payment(
            id=uuid.uuid4(),
            driver_id=payment.driver_id,
            issue_id=payment.issue_id,
            payment_type="platform_fee",
            amount=payment.platform_fee,
            total_amount=payment.total_amount,
            platform_fee=payment.platform_fee,
            currency="GBP",
            stripe_payment_intent_id=payment_intent_id,
            status="completed",
            description=f"Platform commission - Issue {payment.issue_id}"
        )
        
        db.add(platform_payment)
        await db.commit()
        
        # Cache driver earnings in Redis for fast access
        await StripePaymentService._cache_driver_earnings(payment.driver_id, db)
        
        logger.info(f"Payment processed: Driver earning {payment.driver_amount}, Platform fee {payment.platform_fee}")
    
    @staticmethod
    async def _cache_driver_earnings(driver_id: uuid.UUID, db: AsyncSession) -> None:
        """Cache driver total earnings in Redis"""
        redis_client = redis_pool.get_client()
        
        try:
            # Calculate total earnings
            from sqlalchemy import func
            result = await db.execute(
                select(func.sum(DriverEarning.amount)).where(
                    DriverEarning.driver_id == driver_id,
                    DriverEarning.payout_status == "pending"
                )
            )
            total_earnings = result.scalar() or Decimal("0.00")
            
            # Cache for 5 minutes
            cache_key = f"driver_earnings:{driver_id}"
            await redis_client.setex(cache_key, 300, str(total_earnings))
            
        finally:
            await redis_client.close()
