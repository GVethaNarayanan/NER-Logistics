"""
Reusable FastAPI dependencies for authentication and authorization.

Usage in routers:
    from app.dependencies import get_current_user, require_role

    # Any authenticated user
    @router.post("/something")
    def do_thing(user: User = Depends(get_current_user)):
        ...

    # Only admins
    @router.delete("/something/{id}")
    def delete_thing(id: int, user: User = Depends(require_role("admin"))):
        ...
"""
import logging
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth_service import decode_token, get_user_by_username

logger = logging.getLogger("ner_logistics.auth")

# OAuth2PasswordBearer tells Swagger where the login endpoint is so the
# "Authorize" button works. tokenUrl is relative to the app root.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the JWT access token and return the authenticated User.

    Raises 401 for missing/invalid/expired tokens or inactive users.
    Never logs the token value itself.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    # Must be an access token, not a refresh token
    if payload.get("type") != "access":
        raise credentials_exception

    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_role(*allowed_roles: str) -> Callable:
    """Factory that returns a dependency requiring the user to have one of
    the specified roles.

    Usage:
        Depends(require_role("admin"))
        Depends(require_role("admin", "field_official"))
    """

    def _role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            logger.warning(
                "Access denied | user=%s role=%s required=%s",
                user.username,
                user.role,
                allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed_roles)}",
            )
        return user

    return _role_checker
