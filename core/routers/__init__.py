from .auth import router as auth
from .services import router as services

from .bookings import router as bookings
from .driver import router as driver
from .admin import router as admin
from .payments import router as payments

__all__ = ["auth", "services", "bookings", "driver", "admin", "payments"]