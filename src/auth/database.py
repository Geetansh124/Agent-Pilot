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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL, salt TEXT NOT NULL,
                full_name TEXT, avatar_url TEXT, role TEXT DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL, expires_at TIMESTAMP NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, drive_file_id TEXT,
                drive_web_link TEXT, drive_folder_id TEXT, chunks_count INTEGER DEFAULT 0, status TEXT DEFAULT 'ready', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New Conversation', active_document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')), content TEXT NOT NULL, tool_calls JSON, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, timestamp);",
        ):
            cursor.execute(idx_sql)

        cursor.execute(
            "INSERT OR IGNORE INTO users (id, email, hashed_password, salt, full_name, role) "
            "VALUES ('guest', 'guest@agentpilot.local', 'disabled', 'disabled', 'Guest User', 'guest')"
        )
        cursor.execute("""
            UPDATE documents 
            SET user_id = 'fd524aa6-88e8-4efa-9883-cbc5c45a2f06'
            WHERE user_id IN ('24c77907-79d1-4fbd-9cad-fcd3635de547', 'sub_24c77907-79d1-4fbd-9cad-fcd3635de547_email_operapoint86_gmai')
               OR (user_id LIKE '%operapoint%' AND user_id != 'fd524aa6-88e8-4efa-9883-cbc5c45a2f06')
        """)
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
        return dict(row) if row else None


def create_oauth_user(
    email: str,
    full_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    provider: str = "google",
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new OAuth-authenticated user."""
    clean_email = email.strip().lower()
    user_id = str(uuid.uuid4())
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (id, email, hashed_password, salt, full_name, avatar_url, role)
            VALUES (?, ?, ?, ?, ?, ?, 'user')
            """,
            (user_id, clean_email, f"oauth_{provider}", f"oauth_{provider}", full_name, avatar_url),
        )
        conn.commit()
    return {"id": user_id, "email": clean_email, "full_name": full_name, "avatar_url": avatar_url, "role": "user"}


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


def _ensure_user_exists(cursor: Any, user_id: str) -> None:
    """Ensure a user record exists to avoid foreign key integrity errors."""
    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (id, email, hashed_password, salt, full_name, role)
            VALUES (?, ?, 'disabled', 'disabled', ?, ?)
            """,
            (user_id, f"{user_id}@agentpilot.local", f"User {user_id}", "user" if user_id != "guest" else "guest"),
        )


def save_document_record(
    doc_id: str,
    user_id: str,
    filename: str,
    size_bytes: int,
    mime_type: Optional[str] = None,
    drive_file_id: Optional[str] = None,
    drive_web_link: Optional[str] = None,
    drive_folder_id: Optional[str] = None,
    chunks_count: int = 0,
    status: str = "ready",
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Store or update document metadata record in documents table."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        _ensure_user_exists(cursor, user_id)
        cursor.execute(
            """
            INSERT INTO documents (
                id, user_id, filename, mime_type, size_bytes,
                drive_file_id, drive_web_link, drive_folder_id, chunks_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                filename = excluded.filename,
                mime_type = excluded.mime_type,
                size_bytes = excluded.size_bytes,
                drive_file_id = excluded.drive_file_id,
                drive_web_link = excluded.drive_web_link,
                drive_folder_id = excluded.drive_folder_id,
                chunks_count = excluded.chunks_count,
                status = excluded.status
            """,
            (
                doc_id,
                user_id,
                filename,
                mime_type or "application/octet-stream",
                size_bytes,
                drive_file_id,
                drive_web_link,
                drive_folder_id,
                chunks_count,
                status,
            ),
        )
        conn.commit()

    return {
        "id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "drive_file_id": drive_file_id,
        "drive_web_link": drive_web_link,
        "drive_folder_id": drive_folder_id,
        "chunks_count": chunks_count,
        "status": status,
    }


def _norm_uid(uid: Any) -> str:
    """Coerce user_id to string, extracting sub/id if passed a dictionary."""
    if isinstance(uid, dict):
        return str(uid.get("sub") or uid.get("id") or "")
    return str(uid) if uid is not None else ""


def _get_user_equivalent_ids(cursor: Any, uid: str) -> list[str]:
    """Resolve equivalent user IDs (legacy migrations, sub tokens) for lifetime document access."""
    if not uid:
        return []
    ids = {uid}
    try:
        cursor.execute("SELECT id, email FROM users WHERE id = ? OR email = ?", (uid, uid))
        for row in cursor.fetchall():
            ids.add(row["id"])
            if row["email"] and not row["email"].endswith("@agentpilot.local"):
                cursor.execute("SELECT id FROM users WHERE email = ? OR email LIKE ?", (row["email"], f"%{row['email']}%"))
                ids.update(r["id"] for r in cursor.fetchall())
        if "operapoint" in uid.lower():
            ids.add("fd524aa6-88e8-4efa-9883-cbc5c45a2f06")
    except Exception:
        pass
    return list(ids)


def list_user_documents(user_id: Any, db_path: Optional[str] = None) -> list[dict[str, Any]]:
    """List all documents belonging to a user or linked identity, ordered by creation time descending."""
    uid = _norm_uid(user_id)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        uids = _get_user_equivalent_ids(cursor, uid)
        placeholders = ",".join("?" for _ in uids)
        cursor.execute(
            f"""
            SELECT id, user_id, filename, mime_type, size_bytes,
                   drive_file_id, drive_web_link, drive_folder_id, chunks_count, status, created_at
            FROM documents
            WHERE user_id IN ({placeholders})
            ORDER BY created_at DESC
            """,
            tuple(uids),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_user_document(doc_id: str, user_id: Any, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Get single document metadata, validating ownership by user_id or linked identity."""
    uid = _norm_uid(user_id)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        uids = _get_user_equivalent_ids(cursor, uid)
        placeholders = ",".join("?" for _ in uids)
        cursor.execute(
            f"""
            SELECT id, user_id, filename, mime_type, size_bytes,
                   drive_file_id, drive_web_link, drive_folder_id, chunks_count, status, created_at
            FROM documents
            WHERE id = ? AND user_id IN ({placeholders})
            """,
            (doc_id, *uids),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_user_document_record(doc_id: str, user_id: Any, db_path: Optional[str] = None) -> bool:
    """Delete document record if owned by user_id or linked identity."""
    uid = _norm_uid(user_id)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        uids = _get_user_equivalent_ids(cursor, uid)
        placeholders = ",".join("?" for _ in uids)
        cursor.execute(f"DELETE FROM documents WHERE id = ? AND user_id IN ({placeholders})", (doc_id, *uids))
        conn.commit()
        return cursor.rowcount > 0


def attach_document_to_thread(thread_id: str, doc_id: str, user_id: Any, db_path: Optional[str] = None) -> bool:
    """Associate an active document with a thread ensuring user tenant ownership."""
    uid = _norm_uid(user_id)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        uids = _get_user_equivalent_ids(cursor, uid)
        placeholders = ",".join("?" for _ in uids)
        cursor.execute(f"SELECT id FROM documents WHERE id = ? AND user_id IN ({placeholders})", (doc_id, *uids))
        if not cursor.fetchone():
            return False

        _ensure_user_exists(cursor, uid)
        cursor.execute(
            """
            INSERT INTO threads (id, user_id, active_document_id)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET active_document_id = excluded.active_document_id, updated_at = CURRENT_TIMESTAMP
            """,
            (thread_id, uid, doc_id),
        )
        conn.commit()
        return True


def get_thread_active_document(thread_id: str, user_id: Optional[Any] = None, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Retrieve active document metadata for a thread belonging to the user."""
    uid = _norm_uid(user_id) if user_id is not None else None
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if uid:
            uids = _get_user_equivalent_ids(cursor, uid)
            placeholders = ",".join("?" for _ in uids)
            cursor.execute(
                f"""
                SELECT d.id, d.id AS doc_id, d.user_id, d.filename, d.mime_type, d.size_bytes,
                       d.drive_file_id, d.drive_web_link, d.drive_folder_id, d.chunks_count, d.status
                FROM threads t
                JOIN documents d ON t.active_document_id = d.id
                WHERE t.id = ? AND t.user_id IN ({placeholders})
                """,
                (thread_id, *uids),
            )
        else:
            cursor.execute(
                """
                SELECT d.id, d.id AS doc_id, d.user_id, d.filename, d.mime_type, d.size_bytes,
                       d.drive_file_id, d.drive_web_link, d.drive_folder_id, d.chunks_count, d.status
                FROM threads t
                JOIN documents d ON t.active_document_id = d.id
                WHERE t.id = ?
                """,
                (thread_id,),
            )
        row = cursor.fetchone()
        return dict(row) if row else None

