"""Password hashing (argon2), recruiter JWTs, and single-use candidate invite tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.db import utcnow

JWT_ALGORITHM = "HS256"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    recruiter_id: int, secret: str, ttl_minutes: int, now: datetime | None = None
) -> str:
    issued = now or utcnow()
    claims = {
        "sub": str(recruiter_id),
        "iat": issued,
        "exp": issued + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> int:
    """Return the recruiter id. Raises jwt.InvalidTokenError for bad or expired tokens."""
    claims = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp"]})
    return int(claims["sub"])


def hash_invite_token(token: str) -> str:
    """Only this hash is stored, so a database leak does not leak working invite links."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_invite_token() -> tuple[str, str]:
    """Return (raw token for the link, hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_invite_token(token)
