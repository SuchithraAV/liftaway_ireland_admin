from pydantic import BaseModel, EmailStr, Field, validator, model_serializer
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal
from core.models import UserRole, BookingStatus, PaymentStatus, ApprovalStatus, IssueStatus, IssuePaymentStatus

# Customer Registration Schema
class CustomerCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
    address: str
    password: str

# Driver Registration Schema - Step by step
class DriverPersonalDetails(BaseModel):
    full_name: str
    phone_number: str
    email: EmailStr
    dob: Optional[str] = None
    address: str

class DriverIdentityVerification(BaseModel):
    govt_id_type: str
    govt_id_number: str
    id_photo_url: Optional[str] = None
    selfie_photo_url: Optional[str] = None

class DriverProfessionalDetails(BaseModel):
    years_experience: int
    license_number: str
    license_category: str
    license_expiry_date: str

class DriverVehicleDetails(BaseModel):
    vehicle_type: str  # truck, van, auto, e-cart
    vehicle_number_plate: str
    vehicle_model: str
    vehicle_capacity: str
    rc_book_pic_url: Optional[str] = None
    pollution_cert_pic_url: Optional[str] = None

class DriverServiceAreaDetails(BaseModel):
    service_pincodes: str  # comma separated
    preferred_shift: str  # morning, evening, full_day, custom

class DriverBankDetails(BaseModel):
    bank_account_number: str
    bank_ifsc: str
    account_holder_name: str
    upi_id: Optional[str] = None

class DriverDocumentUpload(BaseModel):
    driver_photo_url: Optional[str] = None
    license_front_url: Optional[str] = None
    license_back_url: Optional[str] = None
    vehicle_photo_url: Optional[str] = None

class DriverCreate(BaseModel):
    personal_details: DriverPersonalDetails
    identity_verification: DriverIdentityVerification
    professional_details: DriverProfessionalDetails
    vehicle_details: DriverVehicleDetails
    service_area_details: DriverServiceAreaDetails
    bank_details: DriverBankDetails
    document_upload: DriverDocumentUpload
    password: str

# Admin Registration Schema
class AdminCreate(BaseModel):
    phone_number: str
    password: str

# Legacy User Schema for compatibility
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: str

class UserCreate(UserBase):
    password: str
    role: UserRole = UserRole.CUSTOMER

class UserResponse(BaseModel):
    id: UUID
    role: UserRole
    approval_status: str
    is_active: bool
    is_email_verified: Optional[bool] = False
    is_phone_verified: Optional[bool] = False
    date_joined: datetime
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    
    class Config:
        from_attributes = True

# OTP Schemas
class SendOTPRequest(BaseModel):
    phone_number: str

class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp: str

class ResendOTPRequest(BaseModel):
    phone_number: str

# Login Schemas
class MobileLoginRequest(BaseModel):
    phone_number: str

# Auth Schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse
    dashboard_url: str

class TokenData(BaseModel):
    user_id: Optional[str] = None

# Category Schemas
class CategoryCreate(BaseModel):
    name: str
    image_url: str

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

class CategoryResponse(BaseModel):
    id: int
    name: str
    image_url: str
    is_active: bool = True
    created_at: datetime
    
    class Config:
        from_attributes = True
        
    @classmethod
    def model_validate(cls, obj):
        if hasattr(obj, 'is_active') and obj.is_active is None:
            obj.is_active = True
        return super().model_validate(obj)

# Driver Approval Schemas
class DriverApprovalResponse(BaseModel):
    id: UUID
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    approval_status: str
    date_joined: datetime
    
    class Config:
        from_attributes = True

class DriverDetailResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone_number: str
    dob: Optional[datetime] = None
    address: Optional[str] = None
    years_experience: Optional[int] = None

    service_pincodes: Optional[str] = None
    preferred_shift: Optional[str] = None
    approval_status: str
    date_joined: datetime
    
    # Document fields (from driver_documents table)
    govt_id_type: Optional[str] = None
    govt_id_number: Optional[str] = None
    id_photo_url: Optional[str] = None
    selfie_photo_url: Optional[str] = None
    license_number: Optional[str] = None
    license_category: Optional[str] = None
    license_expiry_date: Optional[datetime] = None
    license_front_url: Optional[str] = None
    license_back_url: Optional[str] = None
    driver_photo_url: Optional[str] = None
    
    # Vehicle fields (from driver_vehicle table)
    vehicle_type: Optional[str] = None
    vehicle_number_plate: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_capacity: Optional[str] = None
    vehicle_photo_url: Optional[str] = None
    rc_book_pic_url: Optional[str] = None
    pollution_cert_pic_url: Optional[str] = None
    
    # Bank fields (from driver_bank_details table)
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    account_holder_name: Optional[str] = None
    upi_id: Optional[str] = None
    
    class Config:
        from_attributes = True

class ApprovalRequest(BaseModel):
    action: ApprovalStatus  # approve or reject

# Pagination Schema
class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    per_page: int
    total_pages: int

# User Management Schemas
class UserListResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone_number: str
    is_active: bool
    date_joined: datetime
    is_verified: bool
    
    class Config:
        from_attributes = True

class DriverListResponse(BaseModel):
    id: UUID
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_number_plate: Optional[str] = None
    license_number: Optional[str] = None
    approval_status: str
    is_active: bool
    is_online: bool
    date_joined: datetime
    
    class Config:
        from_attributes = True



# Booking Schemas
class BookingCreate(BaseModel):
    category_id: int
    vehicle_make: str
    vehicle_model: str
    vehicle_reg_number: str
    problem_description: str
    customer_location_lat: float = Field(..., ge=49.9, le=60.9)
    customer_location_lng: float = Field(..., ge=-8.2, le=1.8)

class BookingResponse(BaseModel):
    id: UUID
    customer_id: UUID
    driver_id: Optional[UUID]
    category_id: int
    category_name: Optional[str] = None  # Will be populated from category relationship
    driver_name: Optional[str] = None  # Will be populated from driver relationship
    vehicle_make: str
    vehicle_model: str
    vehicle_reg_number: str
    problem_description: str
    customer_location_lat: float
    customer_location_lng: float
    status: BookingStatus
    status_display: Optional[str] = None  # Human-readable status
    estimated_price: Optional[float]
    final_price: Optional[float]
    payment_status: PaymentStatus
    requested_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class OtpVerifyRequest(BaseModel):
    otp: str

class DriverResponse(BaseModel):
    response: str  # "accept" or "reject"
    
    @validator('response')
    def validate_response(cls, v):
        if v not in ['accept', 'reject']:
            raise ValueError('Response must be "accept" or "reject"')
        return v

class DriverSummaryResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    phone_number: str
    is_active: bool
    average_rating: Optional[float] = None
    total_ratings: int = 0
    
    class Config:
        from_attributes = True

class RatingDetailResponse(BaseModel):
    id: int
    rating: int
    comments: Optional[str]
    created_at: datetime
    customer_name: Optional[str] = None
    
    class Config:
        from_attributes = True

# Location Schemas
class LocationUpdate(BaseModel):
    lat: float = Field(..., ge=49.9, le=60.9)
    lng: float = Field(..., ge=-8.2, le=1.8)

class LocationResponse(BaseModel):
    lat: float
    lng: float
    updated_at: datetime

# Rating Schemas
class RatingCreate(BaseModel):
    booking_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comments: Optional[str] = None

class RatingResponse(BaseModel):
    id: int
    booking_id: UUID
    customer_id: UUID
    technician_id: UUID
    rating: int
    comments: Optional[str]
    created_at: datetime
    customer_name: Optional[str] = None
    technician_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class BookingWithRatingResponse(BookingResponse):
    rating: Optional[RatingResponse] = None

# Payment Schemas
class PaymentOrderCreate(BaseModel):
    booking_id: UUID

class PaymentOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str

class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    booking_id: UUID

# Profile Schemas
class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

# Email Verification Schemas
class VerifyOTP(BaseModel):
    otp: str

class EmailVerify(BaseModel):
    email: EmailStr
    otp: str

class ResendOTP(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

# OAuth Schemas
class GoogleLoginRequest(BaseModel):
    token: str
    role: UserRole = UserRole.CUSTOMER

class AppleLoginRequest(BaseModel):
    token: str
    role: UserRole = UserRole.CUSTOMER

class SocialLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse
    is_new_user: bool
    dashboard_url: str

# Admin Registration Schema
class AdminCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

# Driver Registration Schema
class DriverCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone_number: str

# Waste Pickup Schemas
class IssueCreate(BaseModel):
    category_id: int
    description: str
    pickup_location: str
    images: Optional[List[str]] = None  # Array of image URLs, max 5
    
    @validator('images')
    def validate_images(cls, v):
        if v and len(v) > 5:
            raise ValueError('Maximum 5 images allowed')
        return v

class IssueResponse(BaseModel):
    id: UUID
    customer_id: UUID
    category_id: int
    category_name: Optional[str] = None
    description: str
    pickup_location: str
    images: Optional[List[str]] = None
    assigned_driver_id: Optional[UUID] = None
    assigned_driver_name: Optional[str] = None
    status: str
    otp_code: str
    payment_amount: Optional[Decimal] = None
    payment_status: str
    scheduled_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class IssueStatusUpdate(BaseModel):
    status: IssueStatus
    otp_code: Optional[str] = None
    
    @validator('otp_code')
    def validate_otp_for_completion(cls, v, values):
        if values.get('status') == IssueStatus.COMPLETED and not v:
            raise ValueError('OTP code is required when changing status to completed')
        return v

class DriverEarningsResponse(BaseModel):
    date: date
    jobs_done: int
    amount: Decimal
    
    class Config:
        from_attributes = True

class DriverIssueResponse(BaseModel):
    id: UUID
    category_name: str
    customer_name: str
    pickup_location: str
    description: str
    images: List[str]
    created_at: datetime
    distance: Optional[float] = None
    payment_amount: Decimal
    status: str
    negotiated_price: Optional[Decimal] = None
    negotiated_status: Optional[str] = None
    scheduled_date: Optional[date] = None
    waiting_time_minutes: Optional[int] = None  # How long customer has been waiting
    
    class Config:
        from_attributes = True

class AcceptIssueRequest(BaseModel):
    driver_lat: float
    driver_lng: float

class NegotiatePriceResponse(BaseModel):
    issue_id: UUID
    payment_amount: Optional[Decimal] = None
    negotiated_price: Optional[Decimal] = None
    negotiated_status: str
    
    class Config:
        from_attributes = True

class NegotiatePriceUpdate(BaseModel):
    status: str  # "approved" or "rejected"
    
    @validator('status')
    def validate_status(cls, v):
        if v.lower() not in ['approved', 'rejected']:
            raise ValueError('Status must be "approved" or "rejected"')
        return v.lower()



# Chat Schemas
class ChatMessageCreate(BaseModel):
    encrypted_text: str

class ChatMessageResponse(BaseModel):
    id: UUID
    issue_id: UUID
    sender_id: UUID
    sender_type: str  # "customer" or "driver"
    text: str  # Decrypted message text (encryption is server-side)
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatHistoryResponse(BaseModel):
    issue_id: UUID
    messages: List[ChatMessageResponse]
    is_chat_active: bool  # False if issue is completed
    
    class Config:
        from_attributes = True

class ChatStatusResponse(BaseModel):
    issue_id: UUID
    is_chat_active: bool
    issue_status: str
    message: str


# Notification Schemas
class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_type: str
    title: str
    message: str
    data: Optional[dict] = None
    is_read: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True