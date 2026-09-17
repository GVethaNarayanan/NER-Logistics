"""
Authentication router — register, login, refresh, and current-user endpoints.

Security notes:
- POST /auth/login accepts OAuth2-compatible form data so Swagger's
  Authorize flow works out of the box.
- Invalid credentials return a generic message (never reveals whether the
  username or password was specifically wrong).
- Passwords and tokens are never logged.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import (
    TokenRefreshRequest,
    TokenResponse,
    UserOut,
    UserRegister,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    decode_token,
    get_user_by_email,
    get_user_by_username,
)

logger = logging.getLogger("ner_logistics.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user.

    - Role is forced to 'field_official' by schema validation (prevents
      privilege escalation).
    - Duplicate username or email returns 409.
    """
    if get_user_by_username(db, payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered",
        )
    if get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = create_user(
        db=db,
        username=payload.username,
        email=payload.email,
        plain_password=payload.password,
        role=payload.role,  # validated by schema to be "field_official"
    )
    return user


# ── Login (OAuth2-compatible form) ────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate and return access + refresh tokens.

    Accepts OAuth2 form fields (username, password) so Swagger's built-in
    Authorize dialog works directly.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        # Generic message — never say "wrong password" or "user not found"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(user.username, user.role)
    refresh_token = create_refresh_token(user.username, user.role)

    logger.info("Login successful: user=%s role=%s", user.username, user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: TokenRefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    decoded = decode_token(payload.refresh_token)
    if decoded is None or decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = decoded.get("sub")
    user = get_user_by_username(db, username) if username else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(user.username, user.role)
    new_refresh = create_refresh_token(user.username, user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=expires_in,
    )


# ── Current user info ─────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
