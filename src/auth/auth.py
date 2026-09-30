"""Authentication and Role-Based Access Control (RBAC).

Provides lightweight, RFC 7519-compatible JWT generation and verification,
password hashing with salt, and user role management.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "docupilot-secret-insecure-key-change-in-prod-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY = int(os.getenv("ACCESS_TOKEN_EXPIRY_SECONDS", "900"))  # 15 minutes default
REFRESH_TOKEN_EXPIRY = int(os.getenv("REFRESH_TOKEN_EXPIRY_SECONDS", str(3600 * 24 * 7)))  # 7 days
DEFAULT_EXPIRY_SECONDS = ACCESS_TOKEN_EXPIRY


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Generate SHA-256 salted password hash."""
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hashed, salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Check whether password matches stored hash and salt."""
    check_hash, _ = hash_password(password, salt=salt)
    return hmac.compare_digest(check_hash, hashed_password)


def create_access_token(
    user_id: str,
    role: str = "user",
    expires_in: int = DEFAULT_EXPIRY_SECONDS,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a signed JWT token."""
    header = {"alg": ALGORITHM, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
        **(extra_claims or {}),
    }

    header_b64 = _base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_and_verify_token(token: str) -> dict[str, Any]:
    """Verify signature and expiration of JWT token, returning payload dict."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token: expected 3 sections.")

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _base64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature.")

    payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
    now = int(time.time())
    if "exp" in payload and payload["exp"] < now:
        raise ValueError("Token has expired.")

    return payload


def hash_token(token: str) -> str:
    """Compute deterministic SHA-256 hash of a token for secure database storage."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def create_refresh_token(expires_in: int = REFRESH_TOKEN_EXPIRY) -> tuple[str, str, str]:
    """Generate high-entropy refresh token, returning (raw_token, token_hash, expires_at_iso)."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    return raw_token, token_hash, expires_at
