"""One-time OAuth2 User Token Generator for Google Drive Storage.

Allows personal @gmail.com Google Drive accounts to be used as persistent storage
and database for Agent-Pilot with your personal 15 GB quota (bypassing the Service Account 0-byte restriction).
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_default_oauth_client() -> tuple[str, str]:
    """Retrieve Client ID and Client Secret from client_secret.json, env, or ADC."""
    secret_file = Path("client_secret.json")
    if secret_file.exists():
        try:
            data = json.loads(secret_file.read_text(encoding="utf-8"))
            info = data.get("installed") or data.get("web") or data
            cid = info.get("client_id", "").strip()
            csec = info.get("client_secret", "").strip()
            if cid and csec:
                return cid, csec
        except Exception:
            pass

    client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "").strip()

    if client_id and client_secret:
        return client_id, client_secret

    adc_path = Path(os.path.expandvars(r"%APPDATA%\gcloud\application_default_credentials.json"))
    if adc_path.exists():
        try:
            data = json.loads(adc_path.read_text(encoding="utf-8"))
            cid = data.get("client_id", "").strip()
            csec = data.get("client_secret", "").strip()
            if cid and csec:
                print("Found Google Cloud credentials in local environment.")
                return cid, csec
        except Exception:
            pass

    return "", ""


def update_env_file(updates: dict[str, str], env_path: str = ".env") -> None:
    """Safely update or append key-value pairs in the .env file."""
    p = Path(env_path)
    if not p.exists():
        p.touch()

    lines = p.read_text(encoding="utf-8").splitlines()
    existing_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                existing_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in existing_keys:
            new_lines.append(f"{key}={val}")

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Updated {env_path} with new configuration.")


from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.parse
import webbrowser

auth_code: Optional[str] = None
server_error: Optional[str] = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, server_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family:system-ui,-apple-system,sans-serif;text-align:center;padding:60px 20px;background:#0b0f19;color:#f8fafc;">
                <div style="max-width:480px;margin:0 auto;background:#1e293b;padding:40px;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:1px solid #334155;">
                    <div style="font-size:48px;margin-bottom:16px;">&#9989;</div>
                    <h2 style="margin:0 0 12px;color:#38bdf8;">Authorization Successful!</h2>
                    <p style="color:#94a3b8;font-size:16px;line-height:1.5;margin:0 0 24px;">Your personal Google Drive storage is now connected to Agent-Pilot.</p>
                    <p style="color:#64748b;font-size:14px;">You can safely close this browser window and return to the terminal.</p>
                </div>
            </body>
            </html>
            """)
        elif "error" in params:
            server_error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            err_msg = html_escape(server_error)
            self.wfile.write(f"<html><body style='font-family:sans-serif;padding:40px;color:red;'><h2>Error: {err_msg}</h2></body></html>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    global auth_code, server_error
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    print("=" * 65, flush=True)
    print(" Agent-Pilot Google Drive User OAuth2 Automated Setup", flush=True)
    print("=" * 65, flush=True)

    client_id, client_secret = get_default_oauth_client()

    if not client_id or not client_secret:
        client_id = input("Enter Google Client ID: ").strip()
        client_secret = input("Enter Google Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Error: Client ID and Client Secret are required.", flush=True)
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing required google-auth-oauthlib...", flush=True)
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth-oauthlib"])
        from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri="http://localhost:8080/",
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    print("\nAuthorization URL:", flush=True)
    print(auth_url, flush=True)
    print("\nOpening browser automatically... Please sign in and grant permission.", flush=True)

    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    httpd.timeout = 1.0

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("Waiting for Google authorization at http://localhost:8080/ ...", flush=True)
    while auth_code is None and server_error is None:
        httpd.handle_request()

    httpd.server_close()

    if server_error:
        print(f"\n[ERROR] Authorization failed: {server_error}", flush=True)
        sys.exit(1)

    print(f"\n[OK] Authorization code received. Exchanging for tokens...", flush=True)
    flow.fetch_token(code=auth_code)
    creds = flow.credentials

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": creds.refresh_token,
        "token": creds.token,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    token_path = Path("google_drive_token.json")
    token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"[OK] Token saved to {token_path.resolve()}", flush=True)

    updates = {
        "STORAGE_BACKEND": "google_drive",
        "GOOGLE_DRIVE_CLIENT_ID": client_id,
        "GOOGLE_DRIVE_CLIENT_SECRET": client_secret,
        "GOOGLE_DRIVE_REFRESH_TOKEN": creds.refresh_token or "",
        "GOOGLE_DRIVE_OAUTH_JSON": "google_drive_token.json",
    }
    update_env_file(updates)

    print("\n[OK] Configuration complete. Verifying Google Drive access...", flush=True)
    try:
        from storage.google_drive import GoogleDriveStorage
        os.environ.update(updates)
        drive = GoogleDriveStorage()
        if drive.health_check():
            print("[SUCCESS] Google Drive health check passed! Personal quota is active.", flush=True)
            test_res = drive.upload_bytes("workspace", "system_test", "health_check.txt", b"Storage ready!")
            print(f"[SUCCESS] Test upload confirmed: {test_res.get('file_id')}", flush=True)
        else:
            print("[WARNING] Drive client initialized but health check returned False.", flush=True)
    except Exception as exc:
        print(f"[WARNING] Verification encountered: {exc}", flush=True)


if __name__ == "__main__":
    main()

