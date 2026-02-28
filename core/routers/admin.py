from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from core.database import get_db
from core.models import UserRole, Category, Driver, ApprovalStatus, Customer, DriverDocument, DriverBankDetail, DriverVehicle
from core.schemas import UserResponse, BookingResponse, RatingResponse, CategoryCreate, CategoryUpdate, CategoryResponse, DriverApprovalResponse, DriverDetailResponse, ApprovalRequest, PaginatedResponse, UserListResponse, DriverListResponse
from core.dependencies import get_current_admin
from core.utils.security import get_password_hash
from core.utils.s3_upload import get_full_url
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin - Ratings"])



@router.post("/categories/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Create new category (admin only)'''
    # Check if category with this name already exists
    result = await db.execute(select(Category).where(Category.name == category_data.name))
    existing_category = result.scalar_one_or_none()
    
    if existing_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with name '{category_data.name}' already exists"
        )
    
    new_category = Category(**category_data.model_dump())
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category

@router.get("/categories/", response_model=List[CategoryResponse])
async def get_all_categories(
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get all categories'''
    result = await db.execute(
        select(Category).order_by(Category.name)
    )
    categories = result.scalars().all()
    
    # Fix null boolean values
    response_categories = []
    for category in categories:
        category_dict = {
            "id": category.id,
            "name": category.name,
            "image_url": category.image_url,
            "is_active": category.is_active if category.is_active is not None else True,
            "created_at": category.created_at
        }
        response_categories.append(CategoryResponse(**category_dict))
    
    return response_categories

@router.put("/categories/{category_id}/", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Update category (admin only)'''
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Update only provided fields
    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    
    await db.commit()
    await db.refresh(category)
    return category

@router.delete("/categories/{category_id}/")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Delete category (admin only)'''
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    await db.delete(category)
    await db.commit()
    
    return {"message": "Category deleted successfully"}

@router.get("/pending-drivers/", response_model=List[DriverApprovalResponse])
async def get_pending_drivers(
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get all pending driver approvals'''
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone
    
    result = await db.execute(
        select(Driver).where(Driver.approval_status == "pending")
        .order_by(Driver.date_joined.desc())
    )
    drivers = result.scalars().all()
    
    decrypted = []
    for driver in drivers:
        decrypted.append(DriverApprovalResponse(
            id=driver.id,
            full_name=decrypt_field(driver.full_name) if driver.full_name else None,
            email=decrypt_email(driver.email) if driver.email else None,
            phone_number=decrypt_phone(driver.phone_number) if driver.phone_number else None,
            approval_status=driver.approval_status,
            date_joined=driver.date_joined
        ))
    return decrypted

@router.get("/pending-drivers/{driver_id}/", response_model=DriverDetailResponse)
async def get_driver_details(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get detailed driver information for verification'''
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone, decrypt_address
    
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Fetch documents
    doc_result = await db.execute(select(DriverDocument).where(DriverDocument.driver_id == driver_id))
    driver_doc = doc_result.scalar_one_or_none()
    
    # Fetch bank details
    bank_result = await db.execute(select(DriverBankDetail).where(DriverBankDetail.driver_id == driver_id))
    bank_detail = bank_result.scalar_one_or_none()
    
    # Fetch vehicle info
    vehicle_result = await db.execute(select(DriverVehicle).where(DriverVehicle.driver_id == driver_id))
    vehicle = vehicle_result.scalar_one_or_none()
    
    # Decrypt data with error handling
    try:
        decrypted_full_name = decrypt_field(driver.full_name) if driver.full_name else None
        logger.info(f"Decrypted full_name: {decrypted_full_name}")
    except Exception as e:
        logger.error(f"Failed to decrypt full_name: {e}")
        decrypted_full_name = driver.full_name
    
    try:
        decrypted_email = decrypt_email(driver.email) if driver.email else None
        logger.info(f"Decrypted email: {decrypted_email}")
    except Exception as e:
        logger.error(f"Failed to decrypt email: {e}")
        decrypted_email = driver.email
    
    try:
        decrypted_phone = decrypt_phone(driver.phone_number) if driver.phone_number else None
        logger.info(f"Decrypted phone: {decrypted_phone}")
    except Exception as e:
        logger.error(f"Failed to decrypt phone: {e}")
        decrypted_phone = driver.phone_number
    
    try:
        decrypted_address = decrypt_address(driver.address) if driver.address else None
    except Exception as e:
        logger.error(f"Failed to decrypt address: {e}")
        decrypted_address = driver.address
    
    # Build response with decrypted data
    response_data = {
        "id": driver.id,
        "full_name": decrypted_full_name,
        "email": decrypted_email,
        "phone_number": decrypted_phone,
        "dob": driver.dob,
        "address": decrypted_address,
        "years_experience": driver.years_experience,
        "service_pincodes": driver.service_pincodes,
        "preferred_shift": driver.preferred_shift,
        "approval_status": driver.approval_status or "pending",
        "date_joined": driver.date_joined,
        # Document fields
        "govt_id_type": driver_doc.govt_id_type if driver_doc else None,
        "govt_id_number": driver_doc.govt_id_number if driver_doc else None,
        "id_photo_url": get_full_url(driver_doc.id_photo_url) if driver_doc and driver_doc.id_photo_url else None,
        "selfie_photo_url": get_full_url(driver_doc.selfie_photo_url) if driver_doc and driver_doc.selfie_photo_url else None,
        "license_number": driver_doc.license_number if driver_doc else None,
        "license_category": driver_doc.license_category if driver_doc else None,
        "license_expiry_date": driver_doc.license_expiry_date if driver_doc else None,
        "license_front_url": get_full_url(driver_doc.license_front_url) if driver_doc and driver_doc.license_front_url else None,
        "license_back_url": get_full_url(driver_doc.license_back_url) if driver_doc and driver_doc.license_back_url else None,
        "driver_photo_url": get_full_url(driver_doc.driver_photo_url) if driver_doc and driver_doc.driver_photo_url else None,
        # Vehicle fields
        "vehicle_type": vehicle.vehicle_type if vehicle else None,
        "vehicle_number_plate": vehicle.vehicle_number_plate if vehicle else None,
        "vehicle_model": vehicle.vehicle_model if vehicle else None,
        "vehicle_capacity": vehicle.vehicle_capacity if vehicle else None,
        "vehicle_photo_url": get_full_url(vehicle.vehicle_photo_url) if vehicle and vehicle.vehicle_photo_url else None,
        "rc_book_pic_url": get_full_url(vehicle.rc_book_pic_url) if vehicle and vehicle.rc_book_pic_url else None,
        "pollution_cert_pic_url": get_full_url(vehicle.pollution_cert_pic_url) if vehicle and vehicle.pollution_cert_pic_url else None,
        # Bank fields
        "bank_account_number": bank_detail.bank_account_number if bank_detail else None,
        "bank_ifsc": bank_detail.bank_ifsc if bank_detail else None,
        "account_holder_name": bank_detail.account_holder_name if bank_detail else None,
        "upi_id": bank_detail.upi_id if bank_detail else None
    }
    
    return response_data

@router.patch("/pending-drivers/{driver_id}/", response_model=DriverApprovalResponse)
async def approve_reject_driver(
    driver_id: UUID,
    approval_data: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Approve or reject driver'''
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    driver.approval_text = approval_data.action.value
    
    await db.commit()
    await db.refresh(driver)
    
    # Send SMS notification
    from core.utils.twilio_service import twilio_service
    if twilio_service and driver.phone_number and admin.phone_number:
        if approval_data.action.value == "approved":
            message = f"Congratulations! Your driver account has been approved by {admin.phone_number}. You can now start accepting jobs."
        else:
            message = f"Your driver account application has been rejected by {admin.phone_number}. Please contact support for more information."
        
        sms_result = twilio_service.send_sms(driver.phone_number, message)
        if sms_result["success"]:
            logger.info(f"SMS sent to driver {driver_id} from admin {admin.phone_number}")
        else:
            logger.warning(f"Failed to send SMS to driver {driver_id}: {sms_result.get('error')}")
    
    return driver
@router.get("/users/", response_model=PaginatedResponse)
async def get_users(
    page: int = 1,
    search: Optional[str] = None,
    sortby: Optional[str] = "date_joined",
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """Get paginated users with search and sort"""
    logger.info(f"Fetching users page={page} search={search}")
    per_page = 10
    offset = (page - 1) * per_page

    # Select only required fields
    query = select(
        Customer.id,
        Customer.full_name,
        Customer.email,
        Customer.phone_number,
        Customer.is_active,
        Customer.date_joined
    )

    # Search filter
    if search:
        query = query.where(
            or_(
                Customer.full_name.ilike(f"%{search}%"),
                Customer.email.ilike(f"%{search}%"),
                Customer.phone_number.ilike(f"%{search}%"),
                Customer.id.ilike(f"%{search}%")
            )
        )

    # Sorting
    if sortby == "name":
        query = query.order_by(Customer.full_name)
    else:
        query = query.order_by(Customer.date_joined.desc())

    # Count total
    count_query = select(func.count(Customer.id))
    if search:
        count_query = count_query.where(
            or_(
                Customer.full_name.ilike(f"%{search}%"),
                Customer.email.ilike(f"%{search}%"),
                Customer.phone_number.ilike(f"%{search}%"),
                Customer.id.ilike(f"%{search}%")
            )
        )

    total = await db.scalar(count_query)

    # Paginated result
    result = await db.execute(query.offset(offset).limit(per_page))
    users_data = result.all()

    # Build response list with decryption
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone
    
    users_list = []
    for user_row in users_data:
        users_list.append({
            "id": user_row.id,
            "full_name": decrypt_field(user_row.full_name) if user_row.full_name else None,
            "email": decrypt_email(user_row.email) if user_row.email else None,
            "phone_number": decrypt_phone(user_row.phone_number) if user_row.phone_number else None,
            "is_active": user_row.is_active,
            "date_joined": user_row.date_joined,
            "role": "customer",
            "is_verified": False
        })

    return PaginatedResponse(
        items=users_list,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page
    )


@router.get("/users/{user_id}/", response_model=UserListResponse)
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """Get specific user details"""
    result = await db.execute(
        select(
            Customer.id,
            Customer.full_name,
            Customer.email,
            Customer.phone_number,
            Customer.is_active,
            Customer.date_joined
        ).where(Customer.id == user_id)
    )

    user_row = result.first()

    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone
    
    user_dict = {
        "id": user_row.id,
        "full_name": decrypt_field(user_row.full_name) if user_row.full_name else None,
        "email": decrypt_email(user_row.email) if user_row.email else None,
        "phone_number": decrypt_phone(user_row.phone_number) if user_row.phone_number else None,
        "is_active": user_row.is_active,
        "date_joined": user_row.date_joined,
        "role": "customer",
        "is_verified": False
    }

    return UserListResponse(**user_dict)


@router.get("/drivers/", response_model=PaginatedResponse)
async def get_drivers(
    page: int = 1,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get paginated drivers with search'''
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone
    
    per_page = 10
    offset = (page - 1) * per_page
    
    query = select(Driver).options(
        selectinload(Driver.vehicles),
        selectinload(Driver.documents)
    )
    
    if search:
        query = query.where(
            or_(
                Driver.full_name.ilike(f"%{search}%"),
                Driver.phone_number.ilike(f"%{search}%"),
                Driver.id.ilike(f"%{search}%")
            )
        )
    
    query = query.order_by(Driver.date_joined.desc())
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Get paginated results
    result = await db.execute(query.offset(offset).limit(per_page))
    drivers = result.scalars().all()
    
    # Decrypt driver data
    decrypted_drivers = []
    for driver in drivers:
        vehicle = driver.vehicles[0] if driver.vehicles else None
        document = driver.documents[0] if driver.documents else None
        
        decrypted_drivers.append({
            "id": driver.id,
            "full_name": decrypt_field(driver.full_name) if driver.full_name else None,
            "email": decrypt_email(driver.email) if driver.email else None,
            "phone_number": decrypt_phone(driver.phone_number) if driver.phone_number else None,
            "vehicle_type": vehicle.vehicle_type if vehicle else None,
            "vehicle_number_plate": vehicle.vehicle_number_plate if vehicle else None,
            "license_number": document.license_number if document else None,
            "approval_status": driver.approval_status,
            "is_active": driver.is_active,
            "is_online": driver.is_online,
            "date_joined": driver.date_joined
        })
    
    return PaginatedResponse(
        items=decrypted_drivers,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page
    )

@router.get("/drivers/{driver_id}/", response_model=DriverDetailResponse)
async def get_driver_full_details(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get specific driver full details'''
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone, decrypt_address
    
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Fetch documents
    doc_result = await db.execute(select(DriverDocument).where(DriverDocument.driver_id == driver_id))
    driver_doc = doc_result.scalar_one_or_none()
    
    # Fetch bank details
    bank_result = await db.execute(select(DriverBankDetail).where(DriverBankDetail.driver_id == driver_id))
    bank_detail = bank_result.scalar_one_or_none()
    
    # Fetch vehicle info
    vehicle_result = await db.execute(select(DriverVehicle).where(DriverVehicle.driver_id == driver_id))
    vehicle = vehicle_result.scalar_one_or_none()
    
    # Build response with full URLs
    return DriverDetailResponse(
        id=driver.id,
        full_name=decrypt_field(driver.full_name) if driver.full_name else None,
        email=decrypt_email(driver.email) if driver.email else None,
        phone_number=decrypt_phone(driver.phone_number) if driver.phone_number else None,
        dob=driver.dob,
        address=decrypt_address(driver.address) if driver.address else None,
        years_experience=driver.years_experience,

        service_pincodes=driver.service_pincodes,
        preferred_shift=driver.preferred_shift,
        approval_status=driver.approval_status or "pending",
        date_joined=driver.date_joined,
        # Document fields
        govt_id_type=driver_doc.govt_id_type if driver_doc else None,
        govt_id_number=driver_doc.govt_id_number if driver_doc else None,
        id_photo_url=get_full_url(driver_doc.id_photo_url) if driver_doc and driver_doc.id_photo_url else None,
        selfie_photo_url=get_full_url(driver_doc.selfie_photo_url) if driver_doc and driver_doc.selfie_photo_url else None,
        license_number=driver_doc.license_number if driver_doc else None,
        license_category=driver_doc.license_category if driver_doc else None,
        license_expiry_date=driver_doc.license_expiry_date if driver_doc else None,
        license_front_url=get_full_url(driver_doc.license_front_url) if driver_doc and driver_doc.license_front_url else None,
        license_back_url=get_full_url(driver_doc.license_back_url) if driver_doc and driver_doc.license_back_url else None,
        driver_photo_url=get_full_url(driver_doc.driver_photo_url) if driver_doc and driver_doc.driver_photo_url else None,
        # Vehicle fields
        vehicle_type=vehicle.vehicle_type if vehicle else None,
        vehicle_number_plate=vehicle.vehicle_number_plate if vehicle else None,
        vehicle_model=vehicle.vehicle_model if vehicle else None,
        vehicle_capacity=vehicle.vehicle_capacity if vehicle else None,
        vehicle_photo_url=get_full_url(vehicle.vehicle_photo_url) if vehicle and vehicle.vehicle_photo_url else None,
        rc_book_pic_url=get_full_url(vehicle.rc_book_pic_url) if vehicle and vehicle.rc_book_pic_url else None,
        pollution_cert_pic_url=get_full_url(vehicle.pollution_cert_pic_url) if vehicle and vehicle.pollution_cert_pic_url else None,
        # Bank fields
        bank_account_number=bank_detail.bank_account_number if bank_detail else None,
        bank_ifsc=bank_detail.bank_ifsc if bank_detail else None,
        account_holder_name=bank_detail.account_holder_name if bank_detail else None,
        upi_id=bank_detail.upi_id if bank_detail else None
    )

@router.get("/bookings/")
async def get_all_issues(
    page: int = 1,
    per_page: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    sortby: Optional[str] = "created_at",
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Get all issues with pagination, search, and sort'''
    from core.models import Issue
    
    offset = (page - 1) * per_page
    
    query = select(Issue).options(
        selectinload(Issue.category),
        selectinload(Issue.customer),
        selectinload(Issue.assigned_driver)
    )
    
    # Search filter
    if search:
        query = query.where(
            or_(
                Issue.id.ilike(f"%{search}%"),
                Issue.pickup_location.ilike(f"%{search}%"),
                Issue.description.ilike(f"%{search}%")
            )
        )
    
    # Status filter
    if status:
        query = query.where(Issue._status == status)
    
    # Sort
    if sortby == "amount":
        query = query.order_by(Issue.payment_amount.desc())
    elif sortby == "status":
        query = query.order_by(Issue._status)
    else:
        query = query.order_by(Issue.created_at.desc())
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Get paginated results
    result = await db.execute(query.offset(offset).limit(per_page))
    issues = result.scalars().all()
    
    # Format response with decryption
    from core.utils.field_encryption import decrypt_field
    
    items = []
    for issue in issues:
        items.append({
            "id": str(issue.id),
            "customer_id": str(issue.customer_id),
            "customer_name": decrypt_field(issue.customer.full_name) if issue.customer and issue.customer.full_name else None,
            "category_id": issue.category_id,
            "category_name": issue.category.name if issue.category else None,
            "description": issue.description,
            "pickup_location": issue.pickup_location,
            "images": issue.images,
            "assigned_driver_id": str(issue.assigned_driver_id) if issue.assigned_driver_id else None,
            "assigned_driver_name": decrypt_field(issue.assigned_driver.full_name) if issue.assigned_driver and issue.assigned_driver.full_name else None,
            "status": issue.status,
            "payment_amount": float(issue.payment_amount),
            "payment_status": issue.payment_status,
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat()
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }

