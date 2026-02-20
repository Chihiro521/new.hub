"""
Security Utilities

Password hashing and JWT token management.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from loguru import logger

from app.core.config import settings

# Password hashing context.
# Keep pbkdf2_sha256 as default for new passwords while allowing
# verification of legacy bcrypt hashes (e.g. existing demo data users).
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password.

    Args:
        password: Plaintext password

    Returns:
        str: Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plaintext password to verify
        hashed_password: Stored password hash

    Returns:
        bool: True if password matches
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        # Compatibility fallback for legacy bcrypt hashes when
        # passlib/bcrypt backend versions are mismatched.
        if isinstance(hashed_password, str) and hashed_password.startswith("$2"):
            try:
                import bcrypt

                return bcrypt.checkpw(
                    plain_password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except Exception as fallback_error:
                logger.warning(
                    "Password verification failed "
                    f"(passlib + bcrypt fallback): {e}; "
                    f"fallback error: {fallback_error}"
                )
                return False

        logger.warning(f"Password verification failed: {e}")
        return False


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: Token subject (typically user_id)
        expires_delta: Custom expiration time
        extra_claims: Additional claims to include

    Returns:
        str: Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.

    Args:
        token: Encoded JWT token

    Returns:
        dict: Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None


def get_token_expiry_seconds() -> int:
    """Get token expiration time in seconds."""
    return settings.access_token_expire_minutes * 60
