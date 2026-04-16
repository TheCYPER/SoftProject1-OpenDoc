import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from jose import JWTError

router = APIRouter(tags=["auth"])

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _create_token(user_id: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(
        {"sub": user_id, "type": token_type, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _create_access_token(user_id: str) -> str:
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def _create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
    )


@router.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new account. Passwords are hashed with PBKDF2-SHA256 (260k rounds)."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        display_name=body.display_name,
        hashed_password=_hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/api/auth/login",
    response_model=TokenResponse,
    summary="Log in and receive an access + refresh token pair",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Exchanges email+password for a 15-min access token and a 7-day refresh token."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    access = _create_access_token(str(user.user_id))
    refresh = _create_refresh_token(str(user.user_id))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access token.

    PoC note: the same refresh token stays valid until its original expiry —
    no rotation or revocation list. Documented in DEVIATIONS.md.
    """
    try:
        payload = jwt.decode(body.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.user_id == user_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return TokenResponse(access_token=_create_access_token(user_id))


@router.get(
    "/api/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
    responses={401: {"description": "Not authenticated or wrong token type"}},
)
async def get_me(current_user: User = Depends(get_current_user)):
    """Access tokens only — refresh tokens are rejected by the dependency."""
    return current_user
