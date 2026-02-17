from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text, TypeDecorator, CHAR, DECIMAL, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import uuid
import enum


# Cross-dialect GUID type: uses Postgres' UUID when available, otherwise CHAR(36)
class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise stores as CHAR(36).
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        # store as string on other dialects
        return str(value)

    def process_result_value(self, value, dialect):
        return value

class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    DRIVER = "driver"
    ADMIN = "admin"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class BookingStatus(str, enum.Enum):
    REQUESTED = "requested"
    PENDING_DRIVER = "pending_driver"
    ACCEPTED = "accepted"
    ON_THE_WAY = "on_the_way"
    ARRIVED = "arrived"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_DRIVER_FOUND = "no_driver_found"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class IssueStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class IssuePaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"

class NegotiatedStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Customer(Base):
    __tablename__ = "customers"
    
    # Use a cross-dialect GUID type so the models work on Postgres and MySQL
    class GUID(TypeDecorator):
        """Platform-independent GUID type.

        Uses Postgresql's UUID type, otherwise stores as CHAR(36).
        """
        impl = CHAR
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == 'postgresql':
                return dialect.type_descriptor(PG_UUID(as_uuid=True))
            else:
                return dialect.type_descriptor(CHAR(36))

        def process_bind_param(self, value, dialect):
            if value is None:
                return value
            if dialect.name == 'postgresql':
                return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
            # store as string on other dialects
            return str(value)

        def process_result_value(self, value, dialect):
            return value

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    address = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    date_joined = Column(DateTime(timezone=True), server_default=func.now())
    




class IssueRating(Base):
    __tablename__ = "issue_ratings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(GUID(), ForeignKey("issues.id"), nullable=False)
    customer_id = Column(GUID(), ForeignKey("customers.id"), nullable=False)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    driver = relationship("Driver", foreign_keys=[driver_id])

class Driver(Base):
    __tablename__ = "drivers"
    
    # Use a cross-dialect GUID type so the models work on Postgres and MySQL
    class GUID(TypeDecorator):
        """Platform-independent GUID type.

        Uses Postgresql's UUID type, otherwise stores as CHAR(36).
        """
        impl = CHAR
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == 'postgresql':
                return dialect.type_descriptor(PG_UUID(as_uuid=True))
            else:
                return dialect.type_descriptor(CHAR(36))

        def process_bind_param(self, value, dialect):
            if value is None:
                return value
            if dialect.name == 'postgresql':
                return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
            # store as string on other dialects
            return str(value)

        def process_result_value(self, value, dialect):
            return value

    # Columns matching the actual database schema for drivers table
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    stripe_account_id = Column(String(255), nullable=True)
    stripe_verification_status = Column(String(50), default="pending")  # pending/verified/failed
    stripe_payouts_enabled = Column(Boolean, default=False)
    stripe_requirements_due = Column(Boolean, default=False)
    stripe_bank_last4 = Column(String(4), nullable=True)  # Last 4 digits for display
    is_approved = Column(String(20), default="pending")
    is_online = Column(Boolean, default=False)
    phone_otp = Column(String(6), nullable=True)
    otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    date_joined = Column(DateTime(timezone=True), server_default=func.now())
    is_phone_verified = Column(Boolean, default=False)
    is_verified = Column(String(20), default="pending")
    dob = Column(DateTime, nullable=True)
    address = Column(Text, nullable=True)
    years_experience = Column(Integer, nullable=True)
    previous_company = Column(String(200), nullable=True)
    service_pincodes = Column(Text, nullable=True)
    preferred_shift = Column(String(50), nullable=True)
    approval_status = Column(String(20), default="pending")
    
    # Note: identity/vehicle/bank/document fields are in separate tables:
    # DriverDocument, DriverBankDetail, DriverVehicle
    
    @property
    def approval_text(self):
        """Always return text approval status"""
        if self.approval_status in ["pending", "approved", "rejected"]:
            return self.approval_status
        return "pending"
    
    @approval_text.setter
    def approval_text(self, value):
        """Set approval status as text"""
        if value in ["pending", "approved", "rejected"]:
            self.approval_status = value
            self.is_approved = value
        else:
            self.approval_status = "pending"
            self.is_approved = "pending"
    
    # Relationships
    location = relationship("DriverLocation", foreign_keys="DriverLocation.driver_id", back_populates="driver", uselist=False)
    wallet_transactions = relationship("DriverWalletTransaction", back_populates="driver")

class Admin(Base):
    __tablename__ = "admins"
    
    # Use a cross-dialect GUID type so the models work on Postgres and MySQL
    class GUID(TypeDecorator):
        """Platform-independent GUID type.

        Uses Postgresql's UUID type, otherwise stores as CHAR(36).
        """
        impl = CHAR
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == 'postgresql':
                return dialect.type_descriptor(PG_UUID(as_uuid=True))
            else:
                return dialect.type_descriptor(CHAR(36))

        def process_bind_param(self, value, dialect):
            if value is None:
                return value
            if dialect.name == 'postgresql':
                return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
            # store as string on other dialects
            return str(value)

        def process_result_value(self, value, dialect):
            return value

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    mobile_otp = Column(String(6), nullable=True)
    otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    date_joined = Column(DateTime(timezone=True), server_default=func.now())



class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    image_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    






class DriverLocation(Base):
    __tablename__ = "driver_locations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), unique=True, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="location")


class DriverDocument(Base):
    __tablename__ = "driver_documents"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    driver_id = Column(GUID(), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    govt_id_type = Column(String(50), nullable=True)
    govt_id_number = Column(String(100), nullable=True)
    id_photo_url = Column(String(500), nullable=True)
    selfie_photo_url = Column(String(500), nullable=True)
    license_number = Column(String(100), nullable=True)
    license_category = Column(String(50), nullable=True)
    license_expiry_date = Column(DateTime, nullable=True)
    license_front_url = Column(String(500), nullable=True)
    license_back_url = Column(String(500), nullable=True)
    driver_photo_url = Column(String(500), nullable=True)

    # Relationships
    driver = relationship("Driver", backref="documents")


class DriverBankDetail(Base):
    __tablename__ = "driver_bank_details"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    driver_id = Column(GUID(), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_account_number = Column(String(100), nullable=True)
    bank_ifsc = Column(String(20), nullable=True)
    account_holder_name = Column(String(200), nullable=True)
    upi_id = Column(String(100), nullable=True)

    # Relationships
    driver = relationship("Driver", backref="bank_details")


class DriverVehicle(Base):
    __tablename__ = "driver_vehicle"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    driver_id = Column(GUID(), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    vehicle_type = Column(String(50), nullable=True)
    vehicle_number_plate = Column(String(50), nullable=True)
    vehicle_model = Column(String(100), nullable=True)
    vehicle_capacity = Column(String(50), nullable=True)
    vehicle_photo_url = Column(String(500), nullable=True)
    rc_book_pic_url = Column(String(500), nullable=True)
    pollution_cert_pic_url = Column(String(500), nullable=True)

    # Relationships
    driver = relationship("Driver", backref="vehicles")



class Issue(Base):
    __tablename__ = "issues"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    customer_id = Column(GUID(), ForeignKey("customers.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    description = Column(Text, nullable=False)
    pickup_location = Column(String(500), nullable=False)
    images = Column(JSON, nullable=False)  # Store array of image URLs as JSON
    assigned_driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=True)
    # Store driver location as a single string "lat,lng" for easy display in customer API
    driver_location = Column(String(100), nullable=True)
    _status = Column("status", String(20), default="pending", nullable=False)
    otp_code = Column(String(6), nullable=False)
    payment_amount = Column(DECIMAL(10, 2), nullable=False)
    _payment_status = Column("payment_status", String(10), default="unpaid", nullable=False)
    negotiated_price = Column(DECIMAL(10, 2), nullable=True)
    _negotiated_status = Column("negotiated_status", String(20), default="pending", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    @property
    def status(self):
        return self._status.lower() if self._status else "pending"
    
    @status.setter
    def status(self, value):
        if hasattr(value, 'value'):
            self._status = value.value.lower()
        else:
            self._status = str(value).lower()
    
    @property
    def payment_status(self):
        return self._payment_status.lower() if self._payment_status else "unpaid"
    
    @payment_status.setter
    def payment_status(self, value):
        if hasattr(value, 'value'):
            self._payment_status = value.value.lower()
        else:
            self._payment_status = str(value).lower()
    
    @property
    def negotiated_status(self):
        return self._negotiated_status.lower() if self._negotiated_status else "pending"
    
    @negotiated_status.setter
    def negotiated_status(self, value):
        if hasattr(value, 'value'):
            self._negotiated_status = value.value.lower()
        else:
            self._negotiated_status = str(value).lower()
    
    # Relationships
    customer = relationship("Customer", foreign_keys=[customer_id])
    category = relationship("Category")
    assigned_driver = relationship("Driver", foreign_keys=[assigned_driver_id])
    earnings = relationship("DriverEarning", back_populates="issue")

class DriverEarning(Base):
    __tablename__ = "driver_earnings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=False)
    issue_id = Column(GUID(), ForeignKey("issues.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    jobs_done = Column(Integer, default=1)
    amount = Column(DECIMAL(10, 2), nullable=False)
    stripe_transfer_id = Column(String(255), nullable=True)
    payout_status = Column(String(20), nullable=False, default="pending")
    available_for_payout = Column(Boolean, default=False)
    
    # Relationships
    driver = relationship("Driver", foreign_keys=[driver_id])
    issue = relationship("Issue", back_populates="earnings")


class ChatMessage(Base):
    """Chat messages between customer and driver for an issue"""
    __tablename__ = "chat_messages"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    issue_id = Column(GUID(), ForeignKey("issues.id"), nullable=False, index=True)
    sender_id = Column(GUID(), nullable=False)  # Can be customer_id or driver_id
    sender_type = Column(String(20), nullable=False)  # "customer" or "driver"
    encrypted_text = Column(Text, nullable=False)  # Store encrypted message
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    issue = relationship("Issue", foreign_keys=[issue_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), nullable=False, index=True)
    user_type = Column(String(20), nullable=False)  # 'customer' or 'driver'
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship helpers can be added if needed


class WalletTransactionType(str, enum.Enum):
    EARNING = "earning"         # Money added from completed job
    WITHDRAWAL = "withdrawal"   # Money withdrawn to bank
    REFUND = "refund"           # Refund from platform
    BONUS = "bonus"             # Platform bonus
    DEDUCTION = "deduction"     # Platform fee deduction


class DriverWalletTransaction(Base):
    """
    Tracks all wallet transactions for drivers.
    Wallet balance = Sum of earnings + bonuses + refunds - withdrawals - deductions
    """
    __tablename__ = "driver_wallet_transactions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # earning/withdrawal/refund/bonus/deduction
    amount = Column(DECIMAL(10, 2), nullable=False)  # Always positive, type determines +/-
    currency = Column(String(3), default="EUR")  # EUR for Euros
    description = Column(String(500), nullable=True)
    
    # Reference to related entities
    issue_id = Column(GUID(), ForeignKey("issues.id"), nullable=True)  # For earnings
    stripe_transfer_id = Column(String(255), nullable=True)  # For withdrawals
    stripe_payout_id = Column(String(255), nullable=True)    # For bank payouts
    
    # Status for withdrawals
    status = Column(String(20), default="completed")  # pending/completed/failed
    failure_reason = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="wallet_transactions")
    issue = relationship("Issue", foreign_keys=[issue_id])


class PaymentType(str, enum.Enum):
    CUSTOMER_PAYMENT = "customer_payment"   # Customer pays for service
    DRIVER_EARNING = "driver_earning"       # Driver earns from completed job
    DRIVER_WITHDRAWAL = "driver_withdrawal" # Driver withdraws to bank
    PLATFORM_FEE = "platform_fee"           # Platform takes fee
    REFUND = "refund"                       # Refund to customer


class Payment(Base):
    """
    Master payments table that tracks all payment flows:
    - Customer payments for issues
    - Driver earnings from completed jobs
    - Driver withdrawals to bank
    - Platform fees
    """
    __tablename__ = "payments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    
    # Payment participants
    customer_id = Column(GUID(), ForeignKey("customers.id"), nullable=True)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=True)
    issue_id = Column(GUID(), ForeignKey("issues.id"), nullable=True)
    
    # Payment details
    payment_type = Column(String(30), nullable=False)  # customer_payment/driver_earning/driver_withdrawal/platform_fee
    amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")  # Euros
    
    # Stripe references
    stripe_payment_intent_id = Column(String(255), nullable=True)
    stripe_transfer_id = Column(String(255), nullable=True)
    stripe_payout_id = Column(String(255), nullable=True)
    stripe_charge_id = Column(String(255), nullable=True)
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending/processing/completed/failed/refunded
    failure_reason = Column(String(500), nullable=True)
    
    # Additional info
    description = Column(String(500), nullable=True)
    extra_data = Column(JSON, nullable=True)  # Any extra data (renamed from metadata - reserved in SQLAlchemy)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    customer = relationship("Customer", foreign_keys=[customer_id])
    driver = relationship("Driver", foreign_keys=[driver_id])
    issue = relationship("Issue", foreign_keys=[issue_id])

class DriverWithdrawRequest(Base):
    __tablename__ = "driver_withdraw_requests"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=False, index=True)
    amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(String(20), default="requested")  # requested/approved/paid/failed
    stripe_transfer_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    driver = relationship("Driver", backref="withdraw_requests")

