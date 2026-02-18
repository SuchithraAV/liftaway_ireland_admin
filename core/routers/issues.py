from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, update
from sqlalchemy.orm import selectinload
from core.database import get_db
from core.models import Issue, Category, Customer, Driver, DriverEarning, IssueStatus, DriverLocation, Notification
from core.schemas import IssueCreate, IssueResponse, IssueStatusUpdate, DriverEarningsResponse, DriverIssueResponse, AcceptIssueRequest, NegotiatePriceResponse, NegotiatePriceUpdate
from core.dependencies import get_current_customer, get_current_driver
from core.chat_websocket import chat_manager
from core.notifications_websocket import notifications_manager
from core.utils.twilio_service import twilio_service
import redis.asyncio as redis
from config import settings
from typing import List, Optional
from uuid import UUID
import random
from datetime import datetime, date
import logging
from core.utils.field_encryption import decrypt_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customer", tags=["Customer Issues"])

# Driver endpoints
driver_router = APIRouter(prefix="/driver", tags=["Driver Issues"])

async def process_scheduled_issues(db: AsyncSession):
    """
    Check for scheduled issues that have reached their date and update them to pending.
    This should be called before querying issues to ensure data is up-to-date.
    """
    try:
        today = date.today()
        # Update scheduled issues where scheduled_date <= today to pending
        await db.execute(
            update(Issue)
            .where(
                Issue._status == "scheduled",
                Issue.scheduled_date <= today
            )
            .values(_status="pending")
        )
        await db.commit()
    except Exception as e:
        # Log error but don't stop the request
        print(f"Error processing scheduled issues: {str(e)}")
        await db.rollback()

@driver_router.get("/issue", response_model=List[DriverIssueResponse])
async def get_driver_issues(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get pending issues for driver with customer details"""
    try:
        # Get driver location for distance calculation
        driver_location = None
        location_result = await db.execute(
            select(DriverLocation).where(DriverLocation.driver_id == current_driver.id)
        )
        driver_location = location_result.scalar_one_or_none()
        
        # Get pending/scheduled issues (only paid issues are visible to drivers)
        # ORDER BY: Oldest first (FIFO queue) - ensures customers who paid first get served first
        result = await db.execute(
            select(Issue)
            .options(selectinload(Issue.category), selectinload(Issue.customer))
            .where(
                Issue._status == "pending",
                Issue._payment_status == "paid"  # Only show paid issues
            )
            .order_by(Issue.created_at.asc())  # ✅ OLDEST FIRST - FIFO Queue
        )
        issues = result.scalars().all()
        
        # Convert to plain data immediately to avoid lazy loading
        issues_data = []
        for issue in issues:
            issues_data.append({
                'id': issue.id,
                'category_name': issue.category.name if issue.category else "Unknown",
                'customer_full_name': issue.customer.full_name if issue.customer else None,
                'pickup_location': issue.pickup_location,
                'description': issue.description,
                'images': issue.images,
                'created_at': issue.created_at,
                'payment_amount': issue.payment_amount,
                '_status': issue._status,
                'negotiated_price': issue.negotiated_price,
                '_negotiated_status': issue._negotiated_status
            })
        
        response_issues = []
        for data in issues_data:
            customer_name = "Unknown"
            if data['customer_full_name']:
                try:
                    customer_name = decrypt_field(data['customer_full_name'])
                except Exception as e:
                    logger.error(f"Failed to decrypt customer name: {e}")
            
            distance = 2.5 if driver_location else None
            waiting_time_minutes = int((datetime.now(data['created_at'].tzinfo) - data['created_at']).total_seconds() / 60)
            
            response_issues.append(DriverIssueResponse(
                id=data['id'],
                category_name=data['category_name'],
                customer_name=customer_name,
                pickup_location=data['pickup_location'],
                description=data['description'],
                images=data['images'] if data['images'] else [],
                created_at=data['created_at'],
                distance=distance,
                payment_amount=float(data['payment_amount']) * 0.80,
                status=data['_status'].lower() if data['_status'] else "pending",
                negotiated_price=float(data['negotiated_price']) * 0.80 if data['negotiated_price'] else None,
                negotiated_status=data['_negotiated_status'].lower() if data['_negotiated_status'] else "pending",
                scheduled_date=None,
                waiting_time_minutes=waiting_time_minutes
            ))
        
        return response_issues
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get issues: {str(e)}")

@driver_router.patch("/issue/{issue_id}/accept", response_model=dict)
async def accept_issue(
    issue_id: UUID,
    accept_data: AcceptIssueRequest,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Driver accepts an issue with location - ATOMIC UPDATE prevents race conditions"""
    try:
        # ATOMIC UPDATE: Only assign if status=pending/scheduled AND assigned_driver_id=NULL AND payment_status=paid
        # This prevents race condition when multiple drivers accept simultaneously
        result = await db.execute(
            update(Issue)
            .where(
                and_(
                    Issue.id == issue_id,
                    Issue._status.in_(["pending", "scheduled"]),
                    Issue.assigned_driver_id.is_(None),  # ✅ Atomic check in WHERE clause
                    Issue._payment_status == "paid"  # ✅ Only accept paid issues
                )
            )
            .values(
                assigned_driver_id=current_driver.id,
                _status="assigned",
                driver_location=f"{accept_data.driver_lat},{accept_data.driver_lng}"
            )
            .returning(Issue.id)
        )
        updated_issue_id = result.scalar_one_or_none()
        
        if not updated_issue_id:
            # Check why update failed
            check_result = await db.execute(select(Issue).where(Issue.id == issue_id))
            issue = check_result.scalar_one_or_none()
            
            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")
            if issue.payment_status != "paid":
                raise HTTPException(status_code=400, detail="Issue payment not completed yet")
            if issue.assigned_driver_id is not None:
                raise HTTPException(status_code=400, detail="Issue has been assigned already")
            if issue.status not in ["pending", "scheduled"]:
                raise HTTPException(status_code=400, detail="Issue not available for assignment")
            raise HTTPException(status_code=500, detail="Failed to assign issue")
        
        # Fetch the updated issue with relationships
        result = await db.execute(
            select(Issue)
            .options(selectinload(Issue.customer))
            .where(Issue.id == issue_id)
        )
        issue = result.scalar_one()
        
        # Update or create driver location
        location_result = await db.execute(
            select(DriverLocation).where(DriverLocation.driver_id == current_driver.id)
        )
        driver_location = location_result.scalar_one_or_none()
        
        if driver_location:
            driver_location.lat = accept_data.driver_lat
            driver_location.lng = accept_data.driver_lng
        else:
            driver_location = DriverLocation(
                driver_id=current_driver.id,
                lat=accept_data.driver_lat,
                lng=accept_data.driver_lng
            )
            db.add(driver_location)
        
        # Get customer details for SMS
        customer = issue.customer
        
        await db.commit()
        
        # Invalidate customer's issue cache so they get fresh data with driver details
        try:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            cache_key = f"customer_issues:{issue.customer_id}"
            await redis_client.delete(cache_key)
            await redis_client.close()
            logger.info(f"✅ Invalidated cache for customer {issue.customer_id}")
        except Exception as e:
            logger.warning(f"⚠️ Cache invalidation failed (non-fatal): {e}")
        
        # Send OTP to customer via Twilio Verify API (same as registration)
        if customer and customer.phone_number and issue.otp_code:
            try:
                if twilio_service:
                    from core.utils.field_encryption import decrypt_phone
                    decrypted_phone = decrypt_phone(customer.phone_number)
                    
                    # Use Twilio Verify API to send OTP
                    otp_result = twilio_service.send_otp(decrypted_phone)
                    if otp_result["success"]:
                        logger.info(f"✅ OTP sent to customer via Twilio Verify")
                    else:
                        logger.error(f"❌ Failed to send OTP: {otp_result.get('error')}")
                else:
                    logger.warning(f"⚠️ Twilio not configured")
            except Exception as e:
                logger.error(f"❌ Failed to send OTP: {str(e)}")
                logger.exception(e)
        
        # Best-effort: create notifications for customer and driver about the assignment
        try:
            # Customer notification: issue approved/assigned by driver WITH DRIVER DETAILS
            cust_note = Notification(
                user_id=issue.customer_id,
                user_type='customer',
                title='Driver Assigned',
                message=f'{current_driver.full_name} has accepted your request and is on the way!',
                data={
                    "issue_id": str(issue.id),
                    "driver_id": str(current_driver.id),
                    "driver_name": current_driver.full_name,
                    "driver_phone": current_driver.phone_number,
                    "driver_lat": accept_data.driver_lat,
                    "driver_lng": accept_data.driver_lng,
                    "status": "assigned",
                    "action": "driver_assigned"  # Frontend can use this to refresh issue details
                }
            )
            db.add(cust_note)

            # Driver notification: new job assigned
            driver_note = Notification(
                user_id=current_driver.id,
                user_type='driver',
                title='New job assigned',
                message=f'You have accepted a new job. Customer is waiting for you.',
                data={"issue_id": str(issue.id)}
            )
            db.add(driver_note)

            await db.commit()
            await db.refresh(cust_note)
            await db.refresh(driver_note)
            
            # Push live notifications via WebSocket
            try:
                await notifications_manager.send_notification(
                    "customer", str(issue.customer_id),
                    {"id": str(cust_note.id), "title": cust_note.title, "message": cust_note.message, "data": cust_note.data, "is_read": False, "created_at": cust_note.created_at.isoformat() if cust_note.created_at else None}
                )
                await notifications_manager.send_notification(
                    "driver", str(current_driver.id),
                    {"id": str(driver_note.id), "title": driver_note.title, "message": driver_note.message, "data": driver_note.data, "is_read": False, "created_at": driver_note.created_at.isoformat() if driver_note.created_at else None}
                )
            except Exception:
                pass
        except Exception:
            # Non-fatal: don't block the accept flow if notifications fail
            try:
                await db.rollback()
            except Exception:
                pass
        
        return {
            "success": True,
            "message": "Issue accepted successfully. OTP sent to customer via SMS.",
            "issue_id": str(issue_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to accept issue: {str(e)}")

@driver_router.put("/issues/{issue_id}/status", response_model=dict)
async def update_issue_status(
    issue_id: UUID,
    status_update: IssueStatusUpdate,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Update issue status"""
    try:
        # Get issue
        result = await db.execute(select(Issue).where(Issue.id == issue_id))
        issue = result.scalar_one_or_none()
        
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        if issue.assigned_driver_id != current_driver.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this issue")
        
        # Get customer for OTP verification
        customer_result = await db.execute(select(Customer).where(Customer.id == issue.customer_id))
        customer = customer_result.scalar_one_or_none()
        
        # Validate status transitions
        if status_update.status == IssueStatus.IN_PROGRESS:
            # Require OTP to start work
            if not status_update.otp_code:
                raise HTTPException(status_code=400, detail="OTP code required to start work")
            
            # Verify OTP via Twilio Verify API
            if twilio_service and customer:
                from core.utils.field_encryption import decrypt_phone
                decrypted_phone = decrypt_phone(customer.phone_number)
                verify_result = twilio_service.verify_otp(decrypted_phone, status_update.otp_code)
                if not verify_result["success"]:
                    raise HTTPException(status_code=400, detail=verify_result.get("error", "Invalid OTP code"))
            else:
                # Fallback to database OTP
                if status_update.otp_code != issue.otp_code:
                    raise HTTPException(status_code=400, detail="Invalid OTP code")
        
        if status_update.status == IssueStatus.COMPLETED:
            # No OTP required for completion - already verified when starting work
            # Just check that work was started (status is in_progress)
            if issue.status != "in_progress":
                raise HTTPException(status_code=400, detail="Issue must be in progress before completion")
            
            # Determine total amount based on negotiated status
            if issue.negotiated_status == "approved" and issue.negotiated_price is not None:
                total_amount = issue.negotiated_price
            else:
                total_amount = issue.payment_amount or 0
            
            # Calculate driver's 80% share
            from decimal import Decimal
            total_decimal = Decimal(str(total_amount))
            driver_amount = (total_decimal * Decimal('0.80')).quantize(Decimal('0.01'))
            
            # Create driver earning record
            earning = DriverEarning(
                driver_id=current_driver.id,
                issue_id=issue.id,
                date=datetime.now(),
                jobs_done=1,
                amount=driver_amount,
                payout_status="pending"
            )
            db.add(earning)
            
            # Close the chat room for this issue
            await chat_manager.close_room(str(issue_id))
        
        # Update status
        issue.status = status_update.status.value
        
        await db.commit()
        # Best-effort notifications for status transitions
        try:
            # Notify customer and driver depending on status
            note_title = None
            note_message = None
            driver_note_title = None
            driver_note_message = None

            new_status = status_update.status
            # If status is an enum member, compare values
            status_value = new_status.value if hasattr(new_status, 'value') else str(new_status)

            if status_value == IssueStatus.IN_PROGRESS.value:
                # Customer: in progress
                note_title = 'Issue in progress'
                note_message = f'Your issue is now being worked on by {current_driver.full_name}.'
                driver_note_title = 'Job started'
                driver_note_message = f'You have started working on this job.'
            elif status_value == IssueStatus.COMPLETED.value:
                note_title = 'Issue completed'
                note_message = f'Your issue has been completed by {current_driver.full_name}. Please leave a review!'
                driver_note_title = 'Job completed'
                driver_note_message = f'Great job! You have completed this issue.'

            if note_title and note_message:
                try:
                    cust_note = Notification(
                        user_id=issue.customer_id,
                        user_type='customer',
                        title=note_title,
                        message=note_message,
                        data={"issue_id": str(issue.id), "status": status_value}
                    )
                    db.add(cust_note)

                    driver_note = Notification(
                        user_id=current_driver.id,
                        user_type='driver',
                        title=driver_note_title,
                        message=driver_note_message,
                        data={"issue_id": str(issue.id), "status": status_value}
                    )
                    db.add(driver_note)

                    await db.commit()
                    await db.refresh(cust_note)
                    await db.refresh(driver_note)
                    
                    # Push live notifications via WebSocket
                    try:
                        await notifications_manager.send_notification(
                            "customer", str(issue.customer_id),
                            {"id": str(cust_note.id), "title": cust_note.title, "message": cust_note.message, "data": cust_note.data, "is_read": False, "created_at": cust_note.created_at.isoformat() if cust_note.created_at else None}
                        )
                        await notifications_manager.send_notification(
                            "driver", str(current_driver.id),
                            {"id": str(driver_note.id), "title": driver_note.title, "message": driver_note.message, "data": driver_note.data, "is_read": False, "created_at": driver_note.created_at.isoformat() if driver_note.created_at else None}
                        )
                    except Exception:
                        pass
                except Exception:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
        except Exception:
            # swallow any issues around notifications
            pass

        # If completed, clear any cached driver location in Redis
        try:
            if status_update.status == IssueStatus.COMPLETED:
                redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                key = f"driver:location:issue:{issue_id}"
                await redis_client.delete(key)
                await redis_client.close()
        except Exception:
            # Non-fatal; log will be captured by exception handler
            pass
        
        return {
            "success": True,
            "message": f"Issue status updated to {status_update.status.value}",
            "issue_id": str(issue_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update issue status: {str(e)}")

@driver_router.get("/earnings", response_model=List[DriverEarningsResponse])
async def get_driver_earnings(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get driver earnings grouped by date"""
    try:
        # Query earnings grouped by date
        result = await db.execute(
            select(
                func.date(DriverEarning.date).label('date'),
                func.count(DriverEarning.id).label('jobs_done'),
                func.sum(DriverEarning.amount).label('amount')
            )
            .where(DriverEarning.driver_id == current_driver.id)
            .group_by(func.date(DriverEarning.date))
            .order_by(desc(func.date(DriverEarning.date)))
        )
        
        earnings_data = result.all()
        
        earnings_list = []
        for earning in earnings_data:
            earnings_list.append(DriverEarningsResponse(
                date=earning.date,
                jobs_done=earning.jobs_done,
                amount=earning.amount or 0
            ))
        
        return earnings_list
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get earnings: {str(e)}")


@driver_router.get("/issues/completed", response_model=List[DriverIssueResponse])
async def get_driver_completed_issues(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get all completed issues for the current driver"""
    try:
        # Get completed issues assigned to this driver
        result = await db.execute(
            select(Issue)
            .options(selectinload(Issue.category), selectinload(Issue.customer))
            .where(
                and_(
                    Issue.assigned_driver_id == current_driver.id,
                    Issue._status == "completed"
                )
            )
            .order_by(desc(Issue.updated_at))
        )
        issues = result.scalars().all()
        
        response_issues = []
        for issue in issues:
            response_data = {
                "id": issue.id,
                "category_name": issue.category.name if issue.category else "Unknown",
                "customer_name": decrypt_field(issue.customer.full_name) if issue.customer and issue.customer.full_name else "Unknown",
                "pickup_location": issue.pickup_location,
                "description": issue.description,
                "images": issue.images if issue.images else [],
                "created_at": issue.created_at,
                "distance": None,
                "payment_amount": float(issue.payment_amount) * 0.80,
                "status": issue.status,
                "negotiated_price": float(issue.negotiated_price) * 0.80 if issue.negotiated_price else None,
                "negotiated_status": issue.negotiated_status,
                "scheduled_date": issue.scheduled_date
            }
            response_issues.append(DriverIssueResponse(**response_data))
        
        return response_issues
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get completed issues: {str(e)}")


@driver_router.get("/issues/my-issues", response_model=List[DriverIssueResponse])
async def get_driver_my_issues(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get all issues assigned to the current driver (in-progress and accepted, not pending)"""
    try:
        # Get all issues assigned to this driver (excluding pending which are available to all)
        result = await db.execute(
            select(Issue)
            .options(selectinload(Issue.category), selectinload(Issue.customer))
            .where(
                and_(
                    Issue.assigned_driver_id == current_driver.id,
                    Issue._status.in_(["assigned", "in_progress"])
                )
            )
            .order_by(desc(Issue.created_at))
        )
        issues = result.scalars().all()
        
        response_issues = []
        for issue in issues:
            response_data = {
                "id": issue.id,
                "category_name": issue.category.name if issue.category else "Unknown",
                "customer_name": decrypt_field(issue.customer.full_name) if issue.customer and issue.customer.full_name else "Unknown",
                "pickup_location": issue.pickup_location,
                "description": issue.description,
                "images": issue.images if issue.images else [],
                "created_at": issue.created_at,
                "distance": None,
                "payment_amount": float(issue.payment_amount) * 0.80,
                "status": issue.status,
                "negotiated_price": float(issue.negotiated_price) * 0.80 if issue.negotiated_price else None,
                "negotiated_status": issue.negotiated_status,
                "scheduled_date": issue.scheduled_date
            }
            response_issues.append(DriverIssueResponse(**response_data))
        
        return response_issues
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get my issues: {str(e)}")


@driver_router.get("/issues/accepted", response_model=List[DriverIssueResponse])
async def get_driver_accepted_issues(
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get issues with status 'assigned' for the current driver only"""
    try:
        result = await db.execute(
            select(Issue)
            .options(selectinload(Issue.category), selectinload(Issue.customer))
            .where(
                and_(
                    Issue.assigned_driver_id == current_driver.id,
                    Issue._status == "assigned"
                )
            )
            .order_by(desc(Issue.created_at))
        )
        issues = result.scalars().all()

        response_issues = []
        for issue in issues:
            response_data = {
                "id": issue.id,
                "category_name": issue.category.name if issue.category else "Unknown",
                "customer_name": decrypt_field(issue.customer.full_name) if issue.customer and issue.customer.full_name else "Unknown",
                "pickup_location": issue.pickup_location,
                "description": issue.description,
                "images": issue.images if issue.images else [],
                "created_at": issue.created_at,
                "distance": None,
                "payment_amount": float(issue.payment_amount) * 0.80,
                "status": issue.status,
                "negotiated_price": float(issue.negotiated_price) * 0.80 if issue.negotiated_price else None,
                "negotiated_status": issue.negotiated_status,
                "scheduled_date": issue.scheduled_date
            }
            response_issues.append(DriverIssueResponse(**response_data))

        return response_issues

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get accepted issues: {str(e)}")


@driver_router.get("/issues/{issue_id}/negotiate_price", response_model=NegotiatePriceResponse)
async def get_negotiate_price(
    issue_id: UUID,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Get negotiation price details for an issue"""
    try:
        # Get issue
        result = await db.execute(select(Issue).where(Issue.id == issue_id))
        issue = result.scalar_one_or_none()
        
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        # Check if driver is assigned to this issue
        if issue.assigned_driver_id != current_driver.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this issue")
        
        return NegotiatePriceResponse(
            issue_id=issue.id,
            payment_amount=issue.payment_amount,
            negotiated_price=issue.negotiated_price,
            negotiated_status=issue.negotiated_status or "pending"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get negotiate price: {str(e)}")


@driver_router.put("/issues/{issue_id}/negotiate_price/update", response_model=dict)
async def update_negotiate_price_status(
    issue_id: UUID,
    update_data: NegotiatePriceUpdate,
    current_driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    """Update negotiation price status (approve or reject)"""
    try:
        # Get issue
        result = await db.execute(select(Issue).where(Issue.id == issue_id))
        issue = result.scalar_one_or_none()
        
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        # Check if driver is assigned to this issue
        if issue.assigned_driver_id != current_driver.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this issue")
        
        # Check if there's a negotiated price to approve/reject
        if issue.negotiated_price is None:
            raise HTTPException(status_code=400, detail="No negotiated price set for this issue")
        
        # Update negotiated status
        issue._negotiated_status = update_data.status
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Negotiated price {update_data.status}",
            "issue_id": str(issue_id),
            "negotiated_price": float(issue.negotiated_price) if issue.negotiated_price else None,
            "negotiated_status": issue.negotiated_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update negotiate price status: {str(e)}")