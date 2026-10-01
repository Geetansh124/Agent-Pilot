"""Authentication middleware and dependencies for FastAPI."""
from __future__ import annotations

from typing import Any, Optional
from fastapi import HTTPException, Request

from src.auth.auth import decode_and_verify_token


def get_current_user(request: Request) -> dict[str, Any]:
    """Extract authenticated user payload from Authorization Bearer header.

    Falls back to a guest user if auth header is absent (allowing flexible access).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return {"sub": "guest", "role": "guest", "is_authenticated": False}

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format. Expected 'Bearer <token>'.")

    token = auth_header[7:].strip()
    try:
        payload = decode_and_verify_token(token)
        payload["is_authenticated"] = True
        if isinstance(payload.get("sub"), dict):
            sub_dict = payload["sub"]
            if "role" in sub_dict and "role" not in payload:
                payload["role"] = sub_dict["role"]
            if "email" in sub_dict and "email" not in payload:
                payload["email"] = sub_dict["email"]
            payload["sub"] = str(sub_dict.get("sub") or sub_dict.get("id") or "")
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc


def require_role(user: dict[str, Any], allowed_roles: tuple[str, ...]) -> None:
    """Enforce role-based access control."""
    role = user.get("role", "guest")
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"Access denied for role '{role}'. Required: {allowed_roles}")


def require_authenticated_user(request: Request) -> dict[str, Any]:
    """Dependency for strictly protected routes requiring a valid authenticated JWT."""
    user = get_current_user(request)
    if not user.get("is_authenticated") or user.get("sub") == "guest":
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided or are invalid.")
    return user
