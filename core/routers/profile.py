from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db

from core.schemas import UserResponse, ProfileUpdate
from core.dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])

@router.get("/", response_model=UserResponse)
async def get_profile(current_user = Depends(get_current_user)):
    '''Get current user profile'''
    from core.models import Customer, Driver, Admin, UserRole
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone
    
    # Determine role based on the type of user object
    if isinstance(current_user, Customer):
        role = UserRole.CUSTOMER
    elif isinstance(current_user, Driver):
        role = UserRole.DRIVER
    elif isinstance(current_user, Admin):
        role = UserRole.ADMIN
    else:
        role = UserRole.CUSTOMER  # fallback
    
    return UserResponse(
        id=current_user.id,
        email=decrypt_email(current_user.email) if getattr(current_user, "email", None) else None,
        full_name=decrypt_field(current_user.full_name) if getattr(current_user, "full_name", None) else None,
        phone_number=decrypt_phone(current_user.phone_number) if getattr(current_user, "phone_number", "") else "",
        role=role,
        is_active=current_user.is_active,
        approval_status=getattr(current_user, "approval_status", "approved"),
        is_email_verified=getattr(current_user, "is_email_verified", False),
        date_joined=current_user.date_joined,

    )

@router.put("/", response_model=UserResponse)
async def update_profile(
    profile_data: ProfileUpdate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    '''Update current user profile'''
    from core.models import Customer, Driver, Admin, UserRole
    from core.utils.field_encryption import decrypt_field, decrypt_email, decrypt_phone, encrypt_field, encrypt_email, encrypt_phone
    
    # Check if email is being changed and if it already exists
    if profile_data.email and hasattr(current_user, 'email'):
        encrypted_new_email = encrypt_email(profile_data.email)
        if current_user.email != encrypted_new_email:
            # Check across all tables
            for model in [Customer, Driver]:
                result = await db.execute(select(model).where(model.email == encrypted_new_email))
                if result.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Email already registered")
    
    # Update fields with encryption
    if profile_data.full_name and hasattr(current_user, 'full_name'):
        current_user.full_name = encrypt_field(profile_data.full_name)
    if profile_data.phone_number and hasattr(current_user, 'phone_number'):
        current_user.phone_number = encrypt_phone(profile_data.phone_number)
    if profile_data.email and hasattr(current_user, 'email'):
        current_user.email = encrypt_email(profile_data.email)
    
    await db.commit()
    await db.refresh(current_user)
    
    # Return UserResponse format with decryption
    if isinstance(current_user, Customer):
        role = UserRole.CUSTOMER
    elif isinstance(current_user, Driver):
        role = UserRole.DRIVER
    elif isinstance(current_user, Admin):
        role = UserRole.ADMIN
    else:
        role = UserRole.CUSTOMER
    
    return UserResponse(
        id=current_user.id,
        email=decrypt_email(current_user.email) if getattr(current_user, "email", None) else None,
        full_name=decrypt_field(current_user.full_name) if getattr(current_user, "full_name", None) else None,
        phone_number=decrypt_phone(current_user.phone_number) if getattr(current_user, "phone_number", "") else "",
        role=role,
        is_active=current_user.is_active,
        approval_status=getattr(current_user, "approval_status", "approved"),
        is_email_verified=getattr(current_user, "is_email_verified", False),
        date_joined=current_user.date_joined,

    )
