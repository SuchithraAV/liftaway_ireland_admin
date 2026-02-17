from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from core.database import get_db
from core.models import IssueRating, Driver
from core.dependencies import get_current_driver

router = APIRouter(prefix="/driver", tags=["Driver Ratings"])

@router.get("/ratings")
async def get_driver_ratings(
    driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get all ratings for current driver"""
    result = await db.execute(
        select(IssueRating).where(IssueRating.driver_id == driver.id).order_by(IssueRating.created_at.desc())
    )
    ratings = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "issue_id": str(r.issue_id),
            "rating": r.rating,
            "comments": r.comments,
            "created_at": r.created_at
        }
        for r in ratings
    ]

@router.get("/ratings/average")
async def get_driver_average_rating(
    driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get average rating for current driver"""
    result = await db.execute(
        select(func.avg(IssueRating.rating), func.count(IssueRating.id))
        .where(IssueRating.driver_id == driver.id)
    )
    avg_rating, count = result.first()
    
    return {
        "driver_id": str(driver.id),
        "average_rating": float(avg_rating) if avg_rating else 0.0,
        "total_ratings": count
    }
