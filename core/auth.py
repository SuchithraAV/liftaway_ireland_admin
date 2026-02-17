from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def _truncate_password_to_72_bytes(password: str) -> str:
    """Return a string that represents at most the first 72 bytes of the
    given password when encoded as UTF-8.

    We do a lossless roundtrip by encoding to bytes then decoding back using
    latin-1. This ensures passlib (which expects a str) receives a value that
    when re-encoded to bytes will be identical to the truncated bytes.
    """
    if password is None:
        return ""
    # Encode to bytes, truncate to 72 bytes, then decode using latin-1 which
    # maps byte values directly to the first 256 unicode codepoints. This
    # avoids introducing or losing bytes when converting back to str for
    # passlib, while ensuring we never pass more than 72 bytes to bcrypt.
    truncated = password.encode("utf-8")[:72]
    return truncated.decode("latin-1")


def verify_password(plain: str, hashed: str) -> bool:
    # Truncate the plain password to 72 bytes before verification to match
    # the behaviour used when hashing.
    return pwd_context.verify(_truncate_password_to_72_bytes(plain), hashed)


def get_password_hash(password: str) -> str:
    # Truncate password to 72 bytes (bcrypt limit) before hashing. We use the
    # same latin-1 decode used in verification to ensure consistent behaviour.
    safe_password = _truncate_password_to_72_bytes(password)
    return pwd_context.hash(safe_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt
