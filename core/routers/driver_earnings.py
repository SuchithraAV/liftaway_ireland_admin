"""
Driver Earnings API - Driver-facing endpoints (hides platform fee)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from core.database import get_db
from core.models import Driver, DriverEarning, Payment
from core.dependencies import get_current_driver
from core.redis_client import redis_pool
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/driver/earnings", tags=["Driver Earnings"])


class DriverEarningResponse(BaseModel):
    """Driver earning response - ONLY shows driver's share"""
    id: int
    issue_id: str
    date: datetime
    amount: float  # Driver's share only (80%)
    payout_status: str
    available_for_payout: bool
    
    class Config:
        from_attributes = True


class EarningsSummaryResponse(BaseModel):
    """Driver earnings summary"""
    total_earnings: float  # Total driver earnings (80% share)
    pending_payout: float  # Available for withdrawal
    completed_jobs: int
    currency: str


@router.get("/summary", response_model=EarningsSummaryResponse)
async def get_earnings_summary(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver earnings summary - ONLY shows driver's share
    Uses Redis cache for fast access
    """
    redis_client = redis_pool.get_client()
    cache_key = f"driver_earnings:{current_driver.id}"
    
    try:
        # Try to get from cache
        cached_earnings = await redis_client.get(cache_key)
        
        if cached_earnings:
            total_earnings = Decimal(cached_earnings)
        else:
            # Calculate from DB
            result = await db.execute(
                select(func.sum(DriverEarning.amount)).where(
                    DriverEarning.driver_id == current_driver.id,
                    DriverEarning.payout_status == "pending"
                )
            )
            total_earnings = result.scalar() or Decimal("0.00")
            
            # Cache for 5 minutes
            await redis_client.setex(cache_key, 300, str(total_earnings))
        
        # Get completed jobs count
        jobs_result = await db.execute(
            select(func.count(DriverEarning.id)).where(
                DriverEarning.driver_id == current_driver.id
            )
        )
        completed_jobs = jobs_result.scalar() or 0
        
        return EarningsSummaryResponse(
            total_earnings=float(total_earnings),
            pending_payout=float(total_earnings),  # Same as total for now
            completed_jobs=completed_jobs,
            currency="GBP"
        )
        
    finally:
        await redis_client.close()


@router.get("/history", response_model=List[DriverEarningResponse])
async def get_earnings_history(
    skip: int = 0,
    limit: int = 50,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver earnings history - ONLY shows driver's share
    Platform fee is NOT exposed to driver
    """
    result = await db.execute(
        select(DriverEarning)
        .where(DriverEarning.driver_id == current_driver.id)
        .order_by(desc(DriverEarning.date))
        .offset(skip)
        .limit(limit)
    )
    earnings = result.scalars().all()
    
    return [
        DriverEarningResponse(
            id=earning.id,
            issue_id=str(earning.issue_id),
            date=earning.date,
            amount=float(earning.amount),  # Driver's share only
            payout_status=earning.payout_status,
            available_for_payout=earning.available_for_payout
        )
        for earning in earnings
    ]


@router.get("/payment-history", response_model=List[dict])
async def get_payment_history(
    skip: int = 0,
    limit: int = 50,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver payment history - ONLY shows driver-related payments
    Platform fee is NOT exposed
    """
    result = await db.execute(
        select(Payment)
        .where(
            Payment.driver_id == current_driver.id,
            Payment.payment_type.in_(["driver_earning", "driver_withdrawal"])
        )
        .order_by(desc(Payment.created_at))
        .offset(skip)
        .limit(limit)
    )
    payments = result.scalars().all()
    
    return [
        {
            "id": str(payment.id),
            "type": payment.payment_type,
            "amount": float(payment.driver_amount or payment.amount),  # Driver's share only
            "currency": payment.currency,
            "status": payment.status,
            "date": payment.created_at,
            "description": payment.description
        }
        for payment in payments
    ]
