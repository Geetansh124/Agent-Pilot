"""Authentication, RBAC, and multi-tenant database package."""
from src.auth.auth import (
    ACCESS_TOKEN_EXPIRY,
    REFRESH_TOKEN_EXPIRY,
    create_access_token,
    create_refresh_token,
    decode_and_verify_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.auth.database import (
    authenticate_user,
    create_user,
    create_oauth_user,
    get_user_by_email,
    get_user_by_id,
    init_auth_db,
    revoke_all_user_refresh_tokens,
    store_refresh_token,
    verify_and_consume_refresh_token,
)
from src.auth.middleware import get_current_user, require_authenticated_user, require_role
from src.auth.routes import auth_router

__all__ = [
    "ACCESS_TOKEN_EXPIRY",
    "REFRESH_TOKEN_EXPIRY",
    "create_access_token",
    "create_refresh_token",
    "decode_and_verify_token",
    "hash_password",
    "hash_token",
    "verify_password",
    "init_auth_db",
    "create_user",
    "authenticate_user",
    "get_user_by_id",
    "get_user_by_email",
    "store_refresh_token",
    "verify_and_consume_refresh_token",
    "revoke_all_user_refresh_tokens",
    "get_current_user",
    "require_authenticated_user",
    "require_role",
    "auth_router",
]
