"""
Driver Dashboard for Waste Management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List
from datetime import date, datetime
from decimal import Decimal

from core.database import get_db
from core.dependencies import get_current_driver
from core.waste_models import WasteJob, DriverDailyEarnings
from core.models import Driver

router = APIRouter(prefix="/driver/waste", tags=["Driver Waste Dashboard"])

class AvailableJobResponse(BaseModel):
    id: str
    load_type: str
    estimated_weight_kg: int
    pickup_address: str
    pickup_postcode: str
    driver_price_gbp: float  # Driver sees 80% of customer price
    estimated_time_minutes: int
    scheduled_pickup_date: datetime
    distance_km: float = 0.0

class EarningsResponse(BaseModel):
    today_earnings: float
    week_earnings: float
    month_earnings: float
    pending_payout: float
    jobs_completed_today: int

@router.get("/available-jobs", response_model=List[AvailableJobResponse])
async def get_available_jobs(
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get available waste collection jobs for driver
    Driver sees 80% of customer price (20% platform fee hidden)
    """
    result = await db.execute(
        select(WasteJob).where(
            WasteJob.status == "pending",
            WasteJob.driver_id.is_(None)
        ).order_by(WasteJob.created_at.desc())
    )
    jobs = result.scalars().all()
    
    return [
        AvailableJobResponse(
            id=str(job.id),
            load_type=job.load_type,
            estimated_weight_kg=job.estimated_weight_kg,
            pickup_address=job.pickup_address,
            pickup_postcode=job.pickup_postcode,
            driver_price_gbp=float(job.driver_price_gbp),  # 80% of customer price
            estimated_time_minutes=job.estimated_time_minutes,
            scheduled_pickup_date=job.scheduled_pickup_date or job.created_at,
            distance_km=0.0  # TODO: Calculate based on driver location
        )
        for job in jobs
    ]

@router.post("/accept-job/{job_id}")
async def accept_job(
    job_id: str,
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Accept a waste collection job"""
    result = await db.execute(
        select(WasteJob).where(
            WasteJob.id == job_id,
            WasteJob.status == "pending",
            WasteJob.driver_id.is_(None)
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not available")
    
    job.driver_id = driver.id
    job.status = "assigned"
    await db.commit()
    
    return {"message": "Job accepted successfully", "job_id": job_id}

@router.get("/earnings", response_model=EarningsResponse)
async def get_driver_earnings(
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver earnings summary
    Shows only driver's 80% share - platform fee is hidden
    """
    today = date.today()
    
    # Today's earnings
    today_result = await db.execute(
        select(func.sum(DriverDailyEarnings.total_earnings_gbp)).where(
            DriverDailyEarnings.driver_id == driver.id,
            DriverDailyEarnings.date == today
        )
    )
    today_earnings = today_result.scalar() or Decimal("0.00")
    
    # Jobs completed today
    jobs_today_result = await db.execute(
        select(func.sum(DriverDailyEarnings.jobs_completed)).where(
            DriverDailyEarnings.driver_id == driver.id,
            DriverDailyEarnings.date == today
        )
    )
    jobs_today = jobs_today_result.scalar() or 0
    
    return EarningsResponse(
        today_earnings=float(today_earnings),
        week_earnings=float(today_earnings * 7),  # Simplified
        month_earnings=float(today_earnings * 30),  # Simplified
        pending_payout=float(today_earnings),
        jobs_completed_today=jobs_today
    )