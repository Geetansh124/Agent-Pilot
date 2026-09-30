"""Database migration and multi-tenant data access models for Agent-Pilot.

Manages relational tables in chatbot.db (users, refresh_tokens, documents,
threads, messages) with SQLite foreign keys and idempotent migrations.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from src.auth.auth import hash_password, verify_password

def get_db_path(db_path: Optional[str] = None) -> str:
    """Resolve database path from argument or CHATBOT_DB_PATH environment variable."""
    return db_path or os.getenv("CHATBOT_DB_PATH", "chatbot.db")


@contextmanager
def get_db_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Create a sqlite connection with foreign keys enabled, ensuring clean closure."""
    target_path = get_db_path(db_path)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_auth_db(db_path: Optional[str] = None) -> None:
    """Idempotently create and migrate all multi-tenant tables and indices."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Users Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT,
                avatar_url TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 2. Refresh Tokens Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 3. Persistent Documents (Google Drive Linked)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                drive_file_id TEXT,
                drive_web_link TEXT,
                drive_folder_id TEXT,
                chunks_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ready',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 4. Chat Threads
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New Conversation',
                active_document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 5. Thread Messages
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                tool_calls JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Indices for optimal query performance and tenant isolation
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id, created_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id, created_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, timestamp);"
        )

        conn.commit()


def create_user(
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = "user",
    avatar_url: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new user account with salted password hashing."""
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Invalid email address format.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters long.")

    user_id = str(uuid.uuid4())
    hashed_pw, salt = hash_password(password)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users (id, email, hashed_password, salt, full_name, avatar_url, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, clean_email, hashed_pw, salt, full_name, avatar_url, role),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: users.email" in str(exc) or "unique" in str(exc).lower():
                raise FileExistsError(f"User with email '{clean_email}' already exists.") from exc
            raise

    return {
        "id": user_id,
        "email": clean_email,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "role": role,
    }


def authenticate_user(
    email: str,
    password: str,
    db_path: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Authenticate user with email and password, returning public user profile."""
    clean_email = email.strip().lower()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, hashed_password, salt, full_name, avatar_url, role, created_at FROM users WHERE email = ?",
            (clean_email,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        if not verify_password(password, row["hashed_password"], row["salt"]):
            return None

        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "avatar_url": row["avatar_url"],
            "role": row["role"],
            "created_at": row["created_at"],
        }


def get_user_by_id(user_id: str, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Retrieve user by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, full_name, avatar_url, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


def get_user_by_email(email: str, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Retrieve user by email."""
    clean_email = email.strip().lower()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, full_name, avatar_url, role, created_at FROM users WHERE email = ?",
            (clean_email,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


def store_refresh_token(
    user_id: str,
    token_hash: str,
    expires_at: str,
    db_path: Optional[str] = None,
) -> str:
    """Store hashed refresh token for a user."""
    token_id = str(uuid.uuid4())
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_id, user_id, token_hash, expires_at),
        )
        conn.commit()
    return token_id


def verify_and_consume_refresh_token(
    token_hash: str,
    db_path: Optional[str] = None,
) -> Optional[str]:
    """Verify refresh token hash against active DB entries and consume it (rotation)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, expires_at FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        # Check expiration
        if row["expires_at"] < now_iso:
            cursor.execute("DELETE FROM refresh_tokens WHERE id = ?", (row["id"],))
            conn.commit()
            return None

        # Rotate: delete old token once consumed
        user_id = row["user_id"]
        cursor.execute("DELETE FROM refresh_tokens WHERE id = ?", (row["id"],))
        conn.commit()
        return user_id


def revoke_all_user_refresh_tokens(user_id: str, db_path: Optional[str] = None) -> None:
    """Revoke all refresh tokens for a user (e.g. upon logout or password reset)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
