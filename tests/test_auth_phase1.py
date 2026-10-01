"""Unit and integration tests for Phase 1: Authentication & Multi-Tenant Database."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient

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
    get_db_connection,
    get_user_by_email,
    get_user_by_id,
    init_auth_db,
    list_user_documents,
    revoke_all_user_refresh_tokens,
    store_refresh_token,
    verify_and_consume_refresh_token,
)
from src.auth.middleware import get_current_user
from src.auth.routes import auth_router
from fastapi import FastAPI


class TestPhase1DatabaseAndAuth(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_chatbot.db")
        init_auth_db(self.db_path)

        # Setup test app for isolated route testing
        self.app = FastAPI()
        self.app.include_router(auth_router, prefix="/api/auth")
        self.client = TestClient(self.app)

        self._orig_env_db = os.environ.get("CHATBOT_DB_PATH")
        os.environ["CHATBOT_DB_PATH"] = self.db_path

    def tearDown(self):
        import gc
        if self._orig_env_db is not None:
            os.environ["CHATBOT_DB_PATH"] = self._orig_env_db
        else:
            os.environ.pop("CHATBOT_DB_PATH", None)
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_idempotent_migration(self):
        """Verifies init_auth_db can run multiple times without error."""
        init_auth_db(self.db_path)
        init_auth_db(self.db_path)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            for expected in ["users", "refresh_tokens", "documents", "threads", "messages"]:
                self.assertIn(expected, tables)

    def test_user_creation_and_password_hashing(self):
        """Tests password salting, hashing, and duplicate detection."""
        user = create_user(
            email="alice@example.com",
            password="securePassword123!",
            full_name="Alice Adams",
            db_path=self.db_path,
        )
        self.assertEqual(user["email"], "alice@example.com")
        self.assertEqual(user["full_name"], "Alice Adams")
        self.assertTrue(user["id"])

        # Duplicate email must raise FileExistsError
        with self.assertRaises(FileExistsError):
            create_user(
                email="ALICE@example.com",  # Case-insensitive
                password="anotherPassword",
                db_path=self.db_path,
            )

        # Short password must raise ValueError
        with self.assertRaises(ValueError):
            create_user(
                email="bob@example.com",
                password="123",
                db_path=self.db_path,
            )

    def test_user_authentication(self):
        """Tests credential authentication against stored hash."""
        create_user(
            email="charlie@example.com",
            password="CharlieSecret99",
            full_name="Charlie C",
            db_path=self.db_path,
        )

        auth_success = authenticate_user("charlie@example.com", "CharlieSecret99", db_path=self.db_path)
        self.assertIsNotNone(auth_success)
        self.assertEqual(auth_success["email"], "charlie@example.com")

        auth_fail_pw = authenticate_user("charlie@example.com", "WrongPassword", db_path=self.db_path)
        self.assertIsNone(auth_fail_pw)

        auth_fail_user = authenticate_user("nonexistent@example.com", "WrongPassword", db_path=self.db_path)
        self.assertIsNone(auth_fail_user)

    def test_jwt_access_and_refresh_tokens(self):
        """Tests JWT creation, signature verification, and expiry claims."""
        token = create_access_token(user_id="user-123", role="user", expires_in=900)
        payload = decode_and_verify_token(token)
        self.assertEqual(payload["sub"], "user-123")
        self.assertEqual(payload["role"], "user")
        self.assertGreater(payload["exp"], payload["iat"])

        raw_refresh, token_hash, expires_at = create_refresh_token(expires_in=604800)
        self.assertEqual(hash_token(raw_refresh), token_hash)

        # Store and consume refresh token
        user = create_user("david@example.com", "Pass12345", db_path=self.db_path)
        token_id = store_refresh_token(user["id"], token_hash, expires_at, db_path=self.db_path)
        self.assertTrue(token_id)

        # First consumption succeeds
        consumed_uid = verify_and_consume_refresh_token(token_hash, db_path=self.db_path)
        self.assertEqual(consumed_uid, user["id"])

        # Second consumption fails (already rotated/consumed)
        reconsumed = verify_and_consume_refresh_token(token_hash, db_path=self.db_path)
        self.assertIsNone(reconsumed)

    def test_foreign_key_cascading(self):
        """Verifies that deleting a user cascades to tokens and threads."""
        user = create_user("eve@example.com", "EvePassword123", db_path=self.db_path)
        _, token_hash, expires_at = create_refresh_token()
        store_refresh_token(user["id"], token_hash, expires_at, db_path=self.db_path)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM refresh_tokens WHERE user_id = ?", (user["id"],))
            self.assertEqual(cursor.fetchone()[0], 1)

            # Delete user
            cursor.execute("DELETE FROM users WHERE id = ?", (user["id"],))
            conn.commit()

            # Refresh tokens should be automatically cascaded
            cursor.execute("SELECT COUNT(*) FROM refresh_tokens WHERE user_id = ?", (user["id"],))
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_api_auth_register_and_login_flow(self):
        """Tests HTTP /api/auth/register and /api/auth/login endpoints."""
        reg_payload = {
            "email": "frank@example.com",
            "password": "FrankStrongPassword!1",
            "full_name": "Frank Castle",
        }
        res = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(data["user"]["email"], "frank@example.com")
        self.assertEqual(data["expires_in"], ACCESS_TOKEN_EXPIRY)

        # Duplicate registration returns 409
        dup_res = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(dup_res.status_code, 409)

        # Login with correct credentials returns 200
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "frank@example.com", "password": "FrankStrongPassword!1"},
        )
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()
        self.assertIn("access_token", login_data)

        # Login with wrong credentials returns 401
        bad_login = self.client.post(
            "/api/auth/login",
            json={"email": "frank@example.com", "password": "wrongpassword"},
        )
        self.assertEqual(bad_login.status_code, 401)

    def test_api_auth_me_protected_endpoint(self):
        """Tests protected /api/auth/me requires valid bearer token."""
        # Unauthenticated request fails with 401
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 401)

        # Register and use token
        reg_res = self.client.post(
            "/api/auth/register",
            json={"email": "grace@example.com", "password": "GracePassword123", "full_name": "Grace Hopper"},
        )
        token = reg_res.json()["access_token"]

        me_res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["email"], "grace@example.com")
        self.assertEqual(me_res.json()["full_name"], "Grace Hopper")

    def test_api_auth_refresh_rotation(self):
        """Tests /api/auth/refresh consumes old refresh token and returns new pair."""
        reg_res = self.client.post(
            "/api/auth/register",
            json={"email": "heidi@example.com", "password": "HeidiSecretPassword"},
        )
        refresh_token = reg_res.json()["refresh_token"]

        ref_res = self.client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        self.assertEqual(ref_res.status_code, 200)
        ref_data = ref_res.json()
        self.assertIn("access_token", ref_data)
        self.assertIn("refresh_token", ref_data)

        # Attempting to reuse old refresh token should fail with 401
        stale_res = self.client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        self.assertEqual(stale_res.status_code, 401)

    def test_dict_user_id_coercion_and_legacy_tokens(self):
        """Verify tokens and database methods handle dictionary inputs and legacy tokens gracefully."""
        user = create_user("dict_test@example.com", "Password123!", db_path=self.db_path)
        token = create_access_token({"sub": user["id"], "email": user["email"], "role": user["role"]})
        payload = decode_and_verify_token(token)
        self.assertEqual(payload["sub"], user["id"])
        self.assertIsInstance(payload["sub"], str)

        docs = list_user_documents({"sub": user["id"]}, db_path=self.db_path)
        self.assertEqual(docs, [])

        class DummyRequest:
            headers = {"Authorization": f"Bearer {token}"}
        current = get_current_user(DummyRequest())
        self.assertEqual(current["sub"], user["id"])
        self.assertIsInstance(current["sub"], str)


if __name__ == "__main__":
    unittest.main()
