from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID
from core.database import get_db

from core.schemas import BookingResponse, BookingWithRatingResponse
from core.dependencies import get_current_user

router = APIRouter(prefix="/bookings", tags=["Admin Bookings"])

def get_status_display(status: str, technician_name: str = None, company_name: str = None) -> str:
    status_messages = {
        "requested": "Service requested - Searching for technician",
        "pending_technician": f"Assigned to {company_name if company_name else (technician_name if technician_name else 'provider')} - Awaiting response",
        "accepted": f"Service approved{f' by {technician_name}' if technician_name else ''} - Technician on the way",
        "on_the_way": f"Technician{f' ({technician_name})' if technician_name else ''} is on the way",
        "arrived": f"Technician{f' ({technician_name})' if technician_name else ''} has arrived",
        "in_progress": f"Service in progress{f' - {technician_name} working' if technician_name else ''}",
        "completed": f"Service completed{f' by {technician_name}' if technician_name else ''}",
        "cancelled": "Service cancelled",
        "no_technician_found": "No technician available at the moment"
    }
    return status_messages.get(status, f"Status: {status}")

@router.get("/", response_model=List[BookingResponse])
async def get_all_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    '''Admin endpoint to view all bookings'''
    result = await db.execute(
        select(BreakdownRequest)
        .options(
            selectinload(BreakdownRequest.service_type),
            selectinload(BreakdownRequest.technician),
            selectinload(BreakdownRequest.company)
        )
        .order_by(BreakdownRequest.requested_at.desc())
    )
    bookings = result.scalars().all()
    
    enhanced_bookings = []
    for booking in bookings:
        technician_name = booking.technician.full_name if booking.technician else None
        company_name = booking.company.name if booking.company else None
        response_data = {
            "id": booking.id,
            "customer_id": booking.customer_id,
            "technician_id": booking.technician_id,
            "company_id": booking.company_id,
            "service_type_id": booking.service_type_id,
            "service_name": booking.service_type.name if booking.service_type else None,
            "technician_name": technician_name,
            "company_name": company_name,
            "vehicle_make": booking.vehicle_make,
            "vehicle_model": booking.vehicle_model,
            "vehicle_reg_number": booking.vehicle_reg_number,
            "problem_description": booking.problem_description,
            "customer_location_lat": booking.customer_location_lat,
            "customer_location_lng": booking.customer_location_lng,
            "status": booking.status,
            "status_display": get_status_display(booking.status, technician_name, company_name),
            "estimated_price": booking.estimated_price,
            "final_price": booking.final_price,
            "payment_status": booking.payment_status,
            "requested_at": booking.requested_at,
            "updated_at": booking.updated_at,
        }
        enhanced_bookings.append(BookingResponse(**response_data))

    return enhanced_bookings

@router.get("/completed/", response_model=List[BookingWithRatingResponse])
async def get_all_completed_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    '''Admin endpoint to view all completed bookings with ratings'''
    result = await db.execute(
        select(BreakdownRequest)
        .options(
            selectinload(BreakdownRequest.service_type),
            selectinload(BreakdownRequest.technician),
            selectinload(BreakdownRequest.company),
            selectinload(BreakdownRequest.rating)
        )
        .where(BreakdownRequest._status == BookingStatus.COMPLETED.value)
        .order_by(BreakdownRequest.updated_at.desc())
    )
    bookings = result.scalars().all()
    
    enhanced_bookings = []
    for booking in bookings:
        technician_name = booking.technician.full_name if booking.technician else None
        company_name = booking.company.name if booking.company else None
        response_data = {
            "id": booking.id,
            "customer_id": booking.customer_id,
            "technician_id": booking.technician_id,
            "company_id": booking.company_id,
            "service_type_id": booking.service_type_id,
            "service_name": booking.service_type.name if booking.service_type else None,
            "technician_name": technician_name,
            "company_name": company_name,
            "vehicle_make": booking.vehicle_make,
            "vehicle_model": booking.vehicle_model,
            "vehicle_reg_number": booking.vehicle_reg_number,
            "problem_description": booking.problem_description,
            "customer_location_lat": booking.customer_location_lat,
            "customer_location_lng": booking.customer_location_lng,
            "status": booking.status,
            "status_display": get_status_display(booking.status, technician_name, company_name),
            "estimated_price": booking.estimated_price,
            "final_price": booking.final_price,
            "payment_status": booking.payment_status,
            "requested_at": booking.requested_at,
            "updated_at": booking.updated_at,
            "rating": None
        }
        
        if booking.rating:
            response_data["rating"] = {
                "id": booking.rating.id,
                "booking_id": booking.rating.booking_id,
                "customer_id": booking.rating.customer_id,
                "technician_id": booking.rating.technician_id,
                "rating": booking.rating.rating,
                "comments": booking.rating.comments,
                "created_at": booking.rating.created_at,
                "customer_name": "Customer",  # For privacy
                "technician_name": technician_name
            }
        
        enhanced_bookings.append(response_data)

    return enhanced_bookings

@router.get("/{booking_id}/", response_model=BookingResponse)
async def get_booking_details(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    '''Admin endpoint to view specific booking details'''
    result = await db.execute(
        select(BreakdownRequest)
        .options(
            selectinload(BreakdownRequest.service_type),
            selectinload(BreakdownRequest.technician),
            selectinload(BreakdownRequest.company)
        )
        .where(BreakdownRequest.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    technician_name = booking.technician.full_name if booking.technician else None
    company_name = booking.company.name if booking.company else None
    response_data = {
        "id": booking.id,
        "customer_id": booking.customer_id,
        "technician_id": booking.technician_id,
        "company_id": booking.company_id,
        "service_type_id": booking.service_type_id,
        "service_name": booking.service_type.name if booking.service_type else None,
        "technician_name": technician_name,
        "company_name": company_name,
        "vehicle_make": booking.vehicle_make,
        "vehicle_model": booking.vehicle_model,
        "vehicle_reg_number": booking.vehicle_reg_number,
        "problem_description": booking.problem_description,
        "customer_location_lat": booking.customer_location_lat,
        "customer_location_lng": booking.customer_location_lng,
        "status": booking.status,
        "status_display": get_status_display(booking.status, technician_name, company_name),
        "estimated_price": booking.estimated_price,
        "final_price": booking.final_price,
        "payment_status": booking.payment_status,
        "requested_at": booking.requested_at,
        "updated_at": booking.updated_at,
    }

    return BookingResponse(**response_data)