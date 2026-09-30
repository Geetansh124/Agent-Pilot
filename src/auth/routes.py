"""Authentication API endpoints for Agent-Pilot.

Provides /api/auth/register, /api/auth/login, /api/auth/refresh, and /api/auth/me.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth.auth import (
    ACCESS_TOKEN_EXPIRY,
    REFRESH_TOKEN_EXPIRY,
    create_access_token,
    create_refresh_token,
    hash_token,
)
from src.auth.database import (
    authenticate_user,
    create_user,
    get_user_by_id,
    revoke_all_user_refresh_tokens,
    store_refresh_token,
    verify_and_consume_refresh_token,
)
from src.auth.middleware import require_authenticated_user

auth_router = APIRouter()

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN, description="Valid user email address")
    password: str = Field(..., min_length=6, max_length=128, description="User password (min 6 characters)")
    full_name: Optional[str] = Field(None, max_length=100, description="Full display name")


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN, description="User email address")
    password: str = Field(..., min_length=1, max_length=128, description="User password")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=256, description="Active refresh token")


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., min_length=1, description="Google OAuth2 ID token credential")


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "user"
    created_at: Optional[str] = None


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRY


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRY


@auth_router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(req: RegisterRequest) -> dict[str, Any]:
    """Register a new user, issue access and refresh tokens."""
    try:
        user = create_user(
            email=req.email,
            password=req.password,
            full_name=req.full_name,
        )
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{req.email}' already exists.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Issue tokens
    access_token = create_access_token(user_id=user["id"], role=user["role"], expires_in=ACCESS_TOKEN_EXPIRY)
    raw_refresh, token_hash, expires_at = create_refresh_token(expires_in=REFRESH_TOKEN_EXPIRY)
    store_refresh_token(user_id=user["id"], token_hash=token_hash, expires_at=expires_at)

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY,
    }


@auth_router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user credentials",
)
def login(req: LoginRequest) -> dict[str, Any]:
    """Validate user credentials and return new session tokens."""
    user = authenticate_user(email=req.email, password=req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue tokens
    access_token = create_access_token(user_id=user["id"], role=user["role"], expires_in=ACCESS_TOKEN_EXPIRY)
    raw_refresh, token_hash, expires_at = create_refresh_token(expires_in=REFRESH_TOKEN_EXPIRY)
    store_refresh_token(user_id=user["id"], token_hash=token_hash, expires_at=expires_at)

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY,
    }


@auth_router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and get a new access token",
)
def refresh_tokens(req: RefreshRequest) -> dict[str, Any]:
    """Consume active refresh token and issue a fresh access/refresh pair."""
    token_hash = hash_token(req.refresh_token)
    user_id = verify_and_consume_refresh_token(token_hash)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already consumed refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    access_token = create_access_token(user_id=user["id"], role=user.get("role", "user"), expires_in=ACCESS_TOKEN_EXPIRY)
    raw_refresh, new_token_hash, expires_at = create_refresh_token(expires_in=REFRESH_TOKEN_EXPIRY)
    store_refresh_token(user_id=user["id"], token_hash=new_token_hash, expires_at=expires_at)

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY,
    }


@auth_router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
def get_current_user_profile(user_claims: dict[str, Any] = Depends(require_authenticated_user)) -> dict[str, Any]:
    """Return profile of the currently authenticated token subject."""
    user_id = user_claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims.")

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return user


@auth_router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke all refresh tokens for current user",
)
def logout(user_claims: dict[str, Any] = Depends(require_authenticated_user)) -> dict[str, str]:
    """Revoke all active refresh tokens for the authenticated user."""
    user_id = user_claims.get("sub")
    if user_id:
        revoke_all_user_refresh_tokens(user_id)
    return {"message": "Successfully logged out."}


@auth_router.post(
    "/google",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in or register using Google 1-Click OAuth ID token",
)
def google_auth(payload: GoogleAuthRequest) -> dict[str, Any]:
    """Verify Google ID token, find or create user, and issue access tokens."""
    import os
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    from src.auth.database import get_user_by_email, create_oauth_user, get_db_connection

    allowed_clients = [
        c.strip() for c in [
            os.getenv("GOOGLE_CLIENT_ID"),
            os.getenv("GOOGLE_DRIVE_CLIENT_ID"),
            "440572861576-iikfhmgbjkd4c8urtnioq0feicu8fpa5.apps.googleusercontent.com",
            "440572861576-r08pagi6ei5qpsmhingll8el0n33iv3h.apps.googleusercontent.com",
        ] if c and c.strip()
    ]
    try:
        id_info = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            audience=allowed_clients if allowed_clients else None,
        )
    except Exception:
        try:
            id_info = id_token.verify_oauth2_token(
                payload.credential,
                google_requests.Request(),
                audience=None,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google authentication failed: {exc}",
            ) from exc

    email = id_info.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No verified email returned from Google.")

    picture = id_info.get("picture")
    name = id_info.get("name")

    user = get_user_by_email(email)
    if not user:
        user = create_oauth_user(
            email=email,
            full_name=name,
            avatar_url=picture,
            provider="google",
        )
    else:
        if picture or name:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE users SET avatar_url = COALESCE(?, avatar_url), full_name = COALESCE(?, full_name), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (picture, name, user["id"]),
                )
                conn.commit()
            user = get_user_by_email(email)

    if user and picture and not user.get("avatar_url"):
        user["avatar_url"] = picture

    access_token = create_access_token({"sub": user["id"], "email": user["email"], "role": user["role"]})
    raw_refresh_token, hashed_refresh, expires_at = create_refresh_token()
    store_refresh_token(user_id=user["id"], token_hash=hashed_refresh, expires_at=expires_at)

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY,
    }

