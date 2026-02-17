from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID
from core.database import get_db

from core.schemas import RatingCreate, RatingResponse
from core.dependencies import get_current_customer

router = APIRouter(prefix="/ratings", tags=["Ratings"])

@router.post("/", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
async def create_rating(
    rating_data: RatingCreate,
    db: AsyncSession = Depends(get_db),
    customer = Depends(get_current_customer)
):
    '''Create rating for completed booking'''
    # Verify booking exists and is completed
    booking_result = await db.execute(
        select(BreakdownRequest).where(
            BreakdownRequest.id == rating_data.booking_id,
            BreakdownRequest.customer_id == customer.id
        )
    )
    booking = booking_result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking.status != BookingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Booking is not completed")
    
    if not booking.technician_id:
        raise HTTPException(status_code=400, detail="No technician assigned to this booking")
    
    # Check if rating already exists
    existing_rating = await db.execute(
        select(Rating).where(Rating.booking_id == rating_data.booking_id)
    )
    if existing_rating.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Rating already exists for this booking")
    
    new_rating = Rating(
        booking_id=rating_data.booking_id,
        customer_id=customer.id,
        technician_id=booking.technician_id,
        rating=rating_data.rating,
        comments=rating_data.comments
    )
    
    db.add(new_rating)
    await db.commit()
    await db.refresh(new_rating)
    
    # Get technician name
    tech_result = await db.execute(
        select(User).where(User.id == booking.technician_id)
    )
    technician = tech_result.scalar_one_or_none()
    
    return {
        "id": new_rating.id,
        "booking_id": new_rating.booking_id,
        "customer_id": new_rating.customer_id,
        "technician_id": new_rating.technician_id,
        "rating": new_rating.rating,
        "comments": new_rating.comments,
        "created_at": new_rating.created_at,
        "customer_name": customer.full_name,
        "technician_name": technician.full_name if technician else None
    }



