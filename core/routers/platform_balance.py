"""
Platform Balance Check - Debug endpoint
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.dependencies import get_current_driver
from core.database import get_db
from core.models import Driver
from uuid import UUID
import stripe
from config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform", tags=["Platform Debug"])

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.get("/balance")
async def get_platform_balance(
    current_driver: Driver = Depends(get_current_driver)
):
    """
    Returns a simple Stripe platform balance:
    - available balance
    - pending balance
    - currency
    """
    try:
        balance = stripe.Balance.retrieve()

        available_balance = 0
        pending_balance = 0
        currency = "USD"

        # Get currency & amount dynamically
        if balance.available:
            available_balance = balance.available[0].amount / 100
            currency = balance.available[0].currency.upper()

        if balance.pending:
            pending_balance = balance.pending[0].amount / 100

        return {
            "platform_available_balance": available_balance,
            "platform_pending_balance": pending_balance,
            "currency": currency
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch platform balance: {str(e)}"
        )


@router.get("/driver/balance/{driver_id}")
async def get_driver_balance(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the Stripe balance for a specific driver using driver_id.
    """
    # Fetch driver from DB
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if not driver.stripe_account_id:
        raise HTTPException(status_code=400, detail="Driver has no Stripe account")

    try:
        # Retrieve driver (connected account) balance
        balance = stripe.Balance.retrieve(
            stripe_account=driver.stripe_account_id
        )

        available_balance = 0
        pending_balance = 0
        currency = "USD"

        if balance.available:
            available_balance = balance.available[0].amount / 100
            currency = balance.available[0].currency.upper()

        if balance.pending:
            pending_balance = balance.pending[0].amount / 100

        return {
            "driver_available_balance": available_balance,
            "driver_pending_balance": pending_balance,
            "currency": currency
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch driver balance: {str(e)}"
        )


