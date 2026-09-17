"""
Authentication service — password hashing and JWT token management.

Security decisions:
- bcrypt used directly for password hashing (passlib is incompatible with
  bcrypt >= 4.1 on Python 3.13; using bcrypt API directly is more reliable)
- python-jose for JWT encode/decode with HS256
- Access tokens: short-lived (configurable, default 30 min)
- Refresh tokens: longer-lived (configurable, default 24 h)
- Token payloads include 'sub' (username), 'role', 'type' (access/refresh)
- No secrets, passwords, or tokens are logged
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

logger = logging.getLogger("ner_logistics.auth")


# ── Password hashing (bcrypt direct) ─────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt. Never log the input."""
    pwd_bytes = plain.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plaintext against stored bcrypt hash. Never log either value."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT token creation ────────────────────────────────────────────────────────

def create_access_token(username: str, role: str) -> tuple[str, int]:
    """Create a short-lived access token. Returns (token_str, expires_in_seconds)."""
    expires_seconds = settings.access_token_expire_minutes * 60
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    payload = {
        "sub": username,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_seconds


def create_refresh_token(username: str, role: str) -> str:
    """Create a longer-lived refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.refresh_token_expire_minutes
    )
    payload = {
        "sub": username,
        "role": role,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT. Returns the payload dict or None on failure."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


# ── User CRUD helpers (used by auth router) ───────────────────────────────────

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Validate credentials. Returns User on success, None on failure.
    Deliberately does not reveal whether the username or password was wrong."""
    user = get_user_by_username(db, username)
    if user is None:
        # Spend time hashing anyway to prevent timing attacks
        hash_password("dummy-timing-safe")
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    plain_password: str,
    role: str = "field_official",
) -> User:
    """Create a new user with hashed password. Caller must check for duplicates."""
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(plain_password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User created: username=%s role=%s", username, role)
    return user
