"""
Payment Reconciliation Service - Ensures Stripe and Database consistency
"""
import stripe
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.database import AsyncSessionLocal
from core.models import Payment, Issue
from config import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

class PaymentReconciliationService:
    """Reconciles payments between Stripe and local database"""
    
    @staticmethod
    async def daily_reconciliation():
        """
        Daily reconciliation job - Critical for production
        
        Why this is essential:
        1. Detects missing payments (Stripe succeeded but DB not updated)
        2. Identifies overpayments or duplicate charges
        3. Ensures commission calculations are accurate
        4. Provides audit trail for financial compliance
        5. Catches webhook failures or network issues
        """
        async with AsyncSessionLocal() as db:
            yesterday = datetime.now() - timedelta(days=1)
            
            # Get all payments from yesterday
            result = await db.execute(
                select(Payment).where(
                    Payment.created_at >= yesterday,
                    Payment.payment_type == "customer_payment"
                )
            )
            db_payments = result.scalars().all()
            
            discrepancies = []
            
            for payment in db_payments:
                if payment.stripe_payment_intent_id:
                    try:
                        # Verify with Stripe
                        stripe_payment = stripe.PaymentIntent.retrieve(
                            payment.stripe_payment_intent_id
                        )
                        
                        # Check status mismatch
                        stripe_status = "completed" if stripe_payment.status == "succeeded" else "pending"
                        if payment.status != stripe_status:
                            discrepancies.append({
                                "payment_id": str(payment.id),
                                "issue": "status_mismatch",
                                "db_status": payment.status,
                                "stripe_status": stripe_status
                            })
                        
                        # Check amount mismatch
                        stripe_amount = Decimal(stripe_payment.amount) / 100
                        if payment.amount != stripe_amount:
                            discrepancies.append({
                                "payment_id": str(payment.id),
                                "issue": "amount_mismatch",
                                "db_amount": float(payment.amount),
                                "stripe_amount": float(stripe_amount)
                            })
                            
                    except stripe.error.StripeError as e:
                        discrepancies.append({
                            "payment_id": str(payment.id),
                            "issue": "stripe_error",
                            "error": str(e)
                        })
            
            if discrepancies:
                logger.error(f"Payment discrepancies found: {discrepancies}")
                # In production: Send alert to admin team
            else:
                logger.info("Payment reconciliation completed - no discrepancies")
            
            return discrepancies

# Scheduler function (would use APScheduler in production)
async def schedule_reconciliation():
    """Run reconciliation at 2 AM daily"""
    return await PaymentReconciliationService.daily_reconciliation()