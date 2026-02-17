from datetime import datetime, timedelta

def get_otp_expiry(minutes: int = 10) -> datetime:
    """Return OTP expiry datetime (UTC)"""
    return datetime.utcnow() + timedelta(minutes=minutes)
