"""
Stripe Connect Webhook Handler

Handles webhook events for:
- account.updated: Driver KYC/verification status changes
- transfer.paid: Transfer to driver completed
- payout.paid: Payout to driver's bank completed
- payout.failed: Payout to driver's bank failed
- payment_intent.succeeded: Customer payment completed
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Issue, DriverWalletTransaction, DriverEarning, Notification
from config import settings
from decimal import Decimal
from datetime import datetime
import stripe
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe-connect", tags=["Stripe Connect Webhooks"])

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/webhook")
async def stripe_connect_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe Connect webhook events.
    
    Important events:
    - account.updated: Driver verification status changed
    - transfer.created/paid: Money transferred to driver
    - payout.paid/failed: Bank payout status
    - payment_intent.succeeded: Customer payment completed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # Verify webhook signature if secret is configured
    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            logger.error("Invalid webhook payload")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # For testing without webhook secret
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})
    
    logger.info(f"Received Stripe webhook: {event_type}")
    
    try:
        if event_type == "account.updated":
            await handle_account_updated(event_data, db)
        
        elif event_type == "transfer.paid":
            await handle_transfer_paid(event_data, db)
        
        elif event_type == "payout.paid":
            await handle_payout_paid(event_data, db)
        
        elif event_type == "payout.failed":
            await handle_payout_failed(event_data, db)
        
        elif event_type == "payment_intent.succeeded":
            await handle_payment_succeeded(event_data, db)
        
        else:
            logger.debug(f"Unhandled event type: {event_type}")
        
        return {"status": "success", "event_type": event_type}
        
    except Exception as e:
        logger.error(f"Error processing webhook {event_type}: {e}")
        # Don't raise - acknowledge receipt to Stripe
        return {"status": "error", "message": str(e)}


async def handle_account_updated(data: dict, db: AsyncSession):
    """
    Handle account.updated event - driver verification status changed.
    
    Updates:
    - stripe_verification_status
    - stripe_payouts_enabled
    """
    stripe_account_id = data.get("id")
    if not stripe_account_id:
        return
    
    # Find driver by Stripe account ID
    result = await db.execute(
        select(Driver).where(Driver.stripe_account_id == stripe_account_id)
    )
    driver = result.scalar_one_or_none()
    
    if not driver:
        logger.warning(f"No driver found for Stripe account {stripe_account_id}")
        return
    
    # Update driver status
    old_payouts_enabled = driver.stripe_payouts_enabled
    
    driver.stripe_payouts_enabled = data.get("payouts_enabled", False)
    
    # Determine verification status
    requirements = data.get("requirements", {})
    if data.get("payouts_enabled"):
        driver.stripe_verification_status = "verified"
    elif requirements.get("disabled_reason"):
        driver.stripe_verification_status = "failed"
    elif requirements.get("currently_due"):
        driver.stripe_verification_status = "pending"
    else:
        driver.stripe_verification_status = "pending"
    
    await db.commit()
    
    logger.info(f"Updated driver {driver.id} Stripe status: verified={driver.stripe_verification_status}, payouts={driver.stripe_payouts_enabled}")
    
    # Notify driver if payouts just became enabled
    if driver.stripe_payouts_enabled and not old_payouts_enabled:
        notification = Notification(
            user_id=driver.id,
            user_type="driver",
            title="Bank Account Verified",
            message="Your bank account has been verified! You can now withdraw your earnings.",
            data={"type": "bank_verified"}
        )
        db.add(notification)
        await db.commit()


async def handle_transfer_paid(data: dict, db: AsyncSession):
    """
    Handle transfer.paid event - money transferred to driver's Stripe account.
    """
    transfer_id = data.get("id")
    destination = data.get("destination")  # Driver's Stripe account
    
    logger.info(f"Transfer {transfer_id} paid to {destination}")
    
    # Update any pending withdrawal transaction
    result = await db.execute(
        select(DriverWalletTransaction).where(
            DriverWalletTransaction.stripe_transfer_id == transfer_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if transaction:
        transaction.status = "completed"
        await db.commit()
        logger.info(f"Updated transaction {transaction.id} status to completed")


async def handle_payout_paid(data: dict, db: AsyncSession):
    """
    Handle payout.paid event - money sent to driver's bank account.
    """
    payout_id = data.get("id")
    stripe_account = data.get("destination")  # This might be the bank account ID
    
    logger.info(f"Payout {payout_id} paid")
    
    # Update transaction if we tracked the payout
    result = await db.execute(
        select(DriverWalletTransaction).where(
            DriverWalletTransaction.stripe_payout_id == payout_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if transaction:
        transaction.status = "completed"
        await db.commit()
        
        # Notify driver
        notification = Notification(
            user_id=transaction.driver_id,
            user_type="driver",
            title="Payout Successful",
            message=f"€{float(transaction.amount):.2f} has been sent to your bank account.",
            data={"type": "payout_success", "amount": float(transaction.amount)}
        )
        db.add(notification)
        await db.commit()


async def handle_payout_failed(data: dict, db: AsyncSession):
    """
    Handle payout.failed event - bank payout failed.
    """
    payout_id = data.get("id")
    failure_code = data.get("failure_code")
    failure_message = data.get("failure_message")
    
    logger.error(f"Payout {payout_id} failed: {failure_code} - {failure_message}")
    
    # Update transaction
    result = await db.execute(
        select(DriverWalletTransaction).where(
            DriverWalletTransaction.stripe_payout_id == payout_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if transaction:
        transaction.status = "failed"
        transaction.failure_reason = f"{failure_code}: {failure_message}"
        await db.commit()
        
        # Notify driver
        notification = Notification(
            user_id=transaction.driver_id,
            user_type="driver",
            title="Payout Failed",
            message=f"Your withdrawal of €{float(transaction.amount):.2f} failed. Please check your bank details.",
            data={"type": "payout_failed", "reason": failure_message}
        )
        db.add(notification)
        await db.commit()
        
        # Refund the amount back to wallet
        refund_transaction = DriverWalletTransaction(
            driver_id=transaction.driver_id,
            transaction_type="refund",
            amount=transaction.amount,
            description=f"Refund for failed payout: {failure_message}",
            status="completed"
        )
        db.add(refund_transaction)
        await db.commit()


async def handle_payment_succeeded(data: dict, db: AsyncSession):
    """
    Handle payment_intent.succeeded - customer payment completed.
    
    This is where we:
    1. Mark the issue as paid
    2. Calculate driver earnings (after platform fee)
    3. Add earning to driver's wallet
    """
    payment_intent_id = data.get("id")
    metadata = data.get("metadata", {})
    amount = data.get("amount_received", 0)  # In pence
    
    issue_id = metadata.get("issue_id")
    driver_id = metadata.get("driver_id")
    
    if not issue_id:
        logger.warning(f"Payment {payment_intent_id} has no issue_id in metadata")
        return
    
    logger.info(f"Payment succeeded for issue {issue_id}: {amount} pence")
    
    # Get the issue
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    
    if not issue:
        logger.error(f"Issue {issue_id} not found")
        return
    
    # Mark issue as paid
    issue.payment_status = "paid"
    
    # Calculate driver earnings (after platform fee)
    platform_fee_percent = getattr(settings, 'PLATFORM_FEE_PERCENT', 20.0)
    driver_share_percent = 100 - platform_fee_percent
    driver_amount_pence = int(amount * driver_share_percent / 100)
    driver_amount_gbp = Decimal(str(driver_amount_pence / 100))
    
    if issue.assigned_driver_id:
        # Create earning record
        earning = DriverEarning(
            driver_id=issue.assigned_driver_id,
            issue_id=issue.id,
            date=datetime.utcnow(),
            jobs_done=1,
            amount=driver_amount_gbp,
            payout_status="pending",
            available_for_payout=True  # Mark as available for payout
        )
        db.add(earning)
        
        # Add to wallet transactions
        wallet_transaction = DriverWalletTransaction(
            driver_id=issue.assigned_driver_id,
            transaction_type="earning",
            amount=driver_amount_gbp,
            description=f"Earnings from job #{str(issue.id)[:8]}",
            issue_id=issue.id,
            status="completed"
        )
        db.add(wallet_transaction)
        
        # Notify driver
        notification = Notification(
            user_id=issue.assigned_driver_id,
            user_type="driver",
            title="Payment Received",
            message=f"You earned €{driver_amount_gbp:.2f} for completing the job.",
            data={
                "type": "payment_received",
                "issue_id": str(issue.id),
                "amount": float(driver_amount_gbp)
            }
        )
        db.add(notification)
    
    await db.commit()
    logger.info(f"Processed payment for issue {issue_id}, driver earning: €{driver_amount_gbp}")


@router.get("/test-webhook")
async def test_webhook():
    """Test endpoint to verify webhook route is accessible"""
    return {
        "status": "ok",
        "message": "Stripe Connect webhook endpoint is ready",
        "webhook_url": "/api/stripe-connect/webhook"
    }
