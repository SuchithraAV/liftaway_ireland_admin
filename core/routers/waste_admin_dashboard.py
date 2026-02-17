"""
Admin Dashboard for Waste Management Platform
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List
from datetime import date, datetime, timedelta
from decimal import Decimal

from core.database import get_db
from core.dependencies import get_current_admin
from core.waste_models import WasteJob, PlatformDailyRevenue, DriverDailyEarnings
from core.models import Admin

router = APIRouter(prefix="/admin/waste", tags=["Admin Waste Dashboard"])

class RevenueResponse(BaseModel):
    today_revenue: float
    week_revenue: float
    month_revenue: float
    total_jobs_today: int
    platform_fees_collected: float
    available_for_withdrawal: float

class JobStatsResponse(BaseModel):
    total_jobs: int
    pending_jobs: int
    completed_jobs: int
    total_revenue: float
    avg_job_value: float

@router.get("/revenue", response_model=RevenueResponse)
async def get_platform_revenue(
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get platform revenue dashboard
    Shows 20% commission collected from all jobs
    """
    today = date.today()
    
    # Today's platform revenue
    today_result = await db.execute(
        select(PlatformDailyRevenue).where(PlatformDailyRevenue.date == today)
    )
    today_revenue = today_result.scalar_one_or_none()
    
    if not today_revenue:
        # Calculate from jobs if daily summary not yet created
        jobs_result = await db.execute(
            select(
                func.count(WasteJob.id),
                func.sum(WasteJob.platform_fee_gbp)
            ).where(
                func.date(WasteJob.created_at) == today,
                WasteJob.payment_status == "paid"
            )
        )
        job_count, platform_fees = jobs_result.first()
        
        return RevenueResponse(
            today_revenue=float(platform_fees or 0),
            week_revenue=float((platform_fees or 0) * 7),  # Simplified
            month_revenue=float((platform_fees or 0) * 30),  # Simplified
            total_jobs_today=job_count or 0,
            platform_fees_collected=float(platform_fees or 0),
            available_for_withdrawal=float(platform_fees or 0)
        )
    
    return RevenueResponse(
        today_revenue=float(today_revenue.platform_fees_collected),
        week_revenue=float(today_revenue.platform_fees_collected * 7),
        month_revenue=float(today_revenue.platform_fees_collected * 30),
        total_jobs_today=today_revenue.total_jobs,
        platform_fees_collected=float(today_revenue.platform_fees_collected),
        available_for_withdrawal=float(today_revenue.platform_fees_collected)
    )

@router.get("/job-stats", response_model=JobStatsResponse)
async def get_job_statistics(
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive job statistics"""
    
    # All time stats
    total_result = await db.execute(
        select(
            func.count(WasteJob.id),
            func.sum(WasteJob.customer_price_gbp),
            func.avg(WasteJob.customer_price_gbp)
        )
    )
    total_jobs, total_revenue, avg_value = total_result.first()
    
    # Status breakdown
    pending_result = await db.execute(
        select(func.count(WasteJob.id)).where(WasteJob.status == "pending")
    )
    pending_jobs = pending_result.scalar()
    
    completed_result = await db.execute(
        select(func.count(WasteJob.id)).where(WasteJob.status == "completed")
    )
    completed_jobs = completed_result.scalar()
    
    return JobStatsResponse(
        total_jobs=total_jobs or 0,
        pending_jobs=pending_jobs or 0,
        completed_jobs=completed_jobs or 0,
        total_revenue=float(total_revenue or 0),
        avg_job_value=float(avg_value or 0)
    )

@router.post("/withdraw-fees")
async def withdraw_platform_fees(
    amount: float,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Withdraw accumulated platform fees to company bank account
    In production: Integrate with Stripe Express payouts
    """
    # Validate available balance
    available_result = await db.execute(
        select(func.sum(PlatformDailyRevenue.platform_fees_collected)).where(
            PlatformDailyRevenue.withdrawal_status == "available"
        )
    )
    available_balance = available_result.scalar() or Decimal("0.00")
    
    if Decimal(str(amount)) > available_balance:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient balance. Available: £{available_balance}"
        )
    
    # TODO: Integrate with Stripe Express payout
    # stripe_payout = stripe.Payout.create(
    #     amount=int(amount * 100),
    #     currency="gbp"
    # )
    
    return {
        "message": f"Withdrawal of £{amount} initiated",
        "remaining_balance": float(available_balance - Decimal(str(amount))),
        "status": "pending"
    }