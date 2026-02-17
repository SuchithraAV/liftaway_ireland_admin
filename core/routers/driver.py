from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from core.database import get_db
from core.models import DriverLocation, UserRole, Driver
from core.schemas import LocationUpdate, LocationResponse, BookingResponse, OtpVerifyRequest, BookingWithRatingResponse, RatingResponse
from core.dependencies import get_current_driver
from core.websocket import manager
from typing import List
import logging
import random

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/driver", tags=["Driver"])

@router.post("/location/", response_model=dict)
async def update_location(
    location_data: LocationUpdate,
    current_user: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(DriverLocation).where(DriverLocation.driver_id == current_user.id)
        result = await db.execute(stmt)
        driver_location = result.scalar_one_or_none()
        
        if driver_location:
            driver_location.lat = location_data.lat
            driver_location.lng = location_data.lng
        else:
            driver_location = DriverLocation(
                driver_id=current_user.id,
                lat=location_data.lat,
                lng=location_data.lng
            )
            db.add(driver_location)
        
        await db.commit()
        await db.refresh(driver_location)
        
        return {
            "success": True,
            "message": "Location updated successfully",
            "location": {
                "lat": driver_location.lat,
                "lng": driver_location.lng,
                "updated_at": driver_location.updated_at
            }
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating driver location: {e}")
        raise HTTPException(status_code=500, detail="Failed to update location")

@router.post("/toggle-online/", response_model=dict)
async def toggle_online_status(
    current_user: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    '''Toggle driver online/offline status'''
    try:
        # Toggle online status (stores as 1/0 in database)
        current_user.is_online = not current_user.is_online
        await db.commit()
        await db.refresh(current_user)
        
        return {
            "success": True,
            "is_online": current_user.is_online,
            "message": f"Status changed to {'online' if current_user.is_online else 'offline'}"
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling online status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update status")

@router.get("/status/", response_model=dict)
async def get_online_status(
    current_user: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    '''Get current online status'''
    from core.utils.field_encryption import decrypt_field, decrypt_email
    
    try:
        return {
            "is_online": current_user.is_online,
            "full_name": decrypt_field(current_user.full_name) if current_user.full_name else None,
            "email": decrypt_email(current_user.email) if current_user.email else None
        }
    except Exception as e:
        logger.error(f"Error getting online status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")

@router.get("/debug/", response_model=dict)
async def debug_driver(
    current_user: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Debug endpoint to check driver status"""
    try:
        return {
            "driver_id": str(current_user.id),
            "full_name": current_user.full_name,
            "is_online": getattr(current_user, 'is_online', False),
            "is_active": current_user.is_active,
            "is_approved": current_user.is_approved
        }
    except Exception as e:
        return {"error": str(e)}













@router.get("/ratings/", response_model=List[RatingResponse])
async def get_my_ratings(
    current_user: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    '''Get all ratings for current driver'''
    try:
        result = await db.execute(
            select(Rating)
            .where(Rating.technician_id == current_user.id)
            .order_by(Rating.created_at.desc())
        )
        ratings = result.scalars().all()
        
        response_ratings = []
        for rating in ratings:
            response_ratings.append({
                "id": rating.id,
                "booking_id": rating.booking_id,
                "customer_id": rating.customer_id,
                "technician_id": rating.technician_id,
                "rating": rating.rating,
                "comments": rating.comments,
                "created_at": rating.created_at,
                "customer_name": "Customer",  # For privacy
                "technician_name": current_user.full_name
            })
        
        return response_ratings
    except Exception as e:
        logger.error(f"Error getting driver ratings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ratings")