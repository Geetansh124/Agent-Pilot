"""Archive all conversation threads partitioned by user ID to JSON and Markdown,
and reset conversation tables in SQLite and Google Drive.
"""
import os
import json
import sqlite3
from datetime import datetime
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# Compatibility shim for langgraph-checkpoint serialization
if not hasattr(JsonPlusSerializer, "loads"):
    JsonPlusSerializer.loads = lambda self, data: (
        self.loads_typed(("json", data))
        if isinstance(data, (bytes, bytearray))
        else (self.loads_typed(("json", str(data).encode("utf-8"))) if data is not None else {})
    )

def export_and_clean_conversations(db_path: str = "chatbot.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Fetch user mapping
    c.execute("SELECT id, email, full_name, role FROM users")
    users = {u[0]: {"id": u[0], "email": u[1], "full_name": u[2], "role": u[3]} for u in c.fetchall()}
    users["guest"] = {"id": "guest", "email": "guest@agentpilot.local", "full_name": "Guest User", "role": "guest"}

    # 2. Extract messages from LangGraph checkpoints
    checkpoint_threads = {}
    try:
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            tuples = list(checkpointer.list(config=None, limit=200))
            for t in tuples:
                tid = t.config["configurable"]["thread_id"]
                msgs = t.checkpoint.get("channel_values", {}).get("messages", [])
                if tid not in checkpoint_threads and msgs:
                    formatted_msgs = []
                    for m in msgs:
                        role = getattr(m, "type", type(m).__name__)
                        content = getattr(m, "content", str(m))
                        formatted_msgs.append({"role": role, "content": content})
                    checkpoint_threads[tid] = formatted_msgs
    except Exception as exc:
        print(f"Warning reading checkpoints: {exc}")

    # 3. Extract threads table
    c.execute("SELECT id, user_id, title, active_document_id, created_at, updated_at FROM threads")
    threads_rows = c.fetchall()

    all_threads = {}
    for tid, uid, title, doc_id, cat, uat in threads_rows:
        # Check messages table
        c.execute("SELECT role, content, timestamp FROM messages WHERE thread_id = ? ORDER BY timestamp ASC", (tid,))
        tbl_msgs = [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in c.fetchall()]

        # Fallback to checkpoint messages if messages table is empty
        final_msgs = tbl_msgs if tbl_msgs else checkpoint_threads.get(tid, [])

        all_threads[tid] = {
            "thread_id": tid,
            "user_id": uid,
            "title": title,
            "active_document_id": doc_id,
            "created_at": cat,
            "updated_at": uat,
            "messages": final_msgs,
        }

    # Add any checkpoint threads that were not registered in threads table
    for tid, msgs in checkpoint_threads.items():
        if tid not in all_threads:
            first_user_msg = next((m["content"] for m in msgs if m.get("role") in ("human", "user")), "New chat")
            title = " ".join(first_user_msg.split())[:48] if isinstance(first_user_msg, str) else "New chat"
            all_threads[tid] = {
                "thread_id": tid,
                "user_id": "guest",
                "title": title,
                "active_document_id": None,
                "created_at": None,
                "updated_at": None,
                "messages": msgs,
            }

    # 4. Group by user
    by_user = {}
    for tid, tdata in all_threads.items():
        uid = tdata["user_id"]
        by_user.setdefault(uid, []).append(tdata)

    archive_payload = {
        "archived_at": datetime.utcnow().isoformat() + "Z",
        "total_conversations": len(all_threads),
        "total_users": len(by_user),
        "users": {},
    }

    for uid, tlist in by_user.items():
        uinfo = users.get(uid, {"id": uid, "email": "unknown", "full_name": "Unknown User", "role": "user"})
        archive_payload["users"][uid] = {
            "user_info": uinfo,
            "conversations_count": len(tlist),
            "conversations": tlist,
        }

    # 5. Write to JSON and Markdown in docs/
    os.makedirs("docs", exist_ok=True)
    json_path = "docs/conversations_history_backup.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(archive_payload, f, indent=2, ensure_ascii=False)
    print(f"Saved full JSON backup to: {json_path}")

    md_path = "docs/conversations_history_backup.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Conversation History Archive\n\n")
        f.write(f"- **Archived At**: {archive_payload['archived_at']}\n")
        f.write(f"- **Total Conversations**: {len(all_threads)}\n")
        f.write(f"- **Users Represented**: {len(by_user)}\n\n---\n\n")

        for uid, udata in archive_payload["users"].items():
            uinfo = udata["user_info"]
            f.write(f"## User: {uinfo.get('full_name', 'Unknown')} (`{uinfo.get('email', 'N/A')}`)\n")
            f.write(f"- **User ID**: `{uid}` | **Total Conversations**: {udata['conversations_count']}\n\n")

            for t in udata["conversations"]:
                f.write(f"### 💬 Thread: {t['title']}\n")
                f.write(f"- **ID**: `{t['thread_id']}` | **Messages**: {len(t['messages'])}\n")
                if not t["messages"]:
                    f.write("*Empty conversation*\n\n")
                    continue
                for msg in t["messages"]:
                    role = msg.get("role", "unknown").capitalize()
                    content = msg.get("content", "").strip()
                    f.write(f"> **{role}**: {content}\n")
                f.write("\n")
            f.write("---\n\n")

    print(f"Saved readable Markdown backup to: {md_path}")

    # 6. Reset conversations tables
    print("\nResetting conversation tables in SQLite...")
    c.execute("DELETE FROM threads")
    c.execute("DELETE FROM messages")
    c.execute("DELETE FROM checkpoints")
    c.execute("DELETE FROM writes")
    c.execute("DELETE FROM thread_metadata")
    conn.commit()
    c.execute("VACUUM")
    conn.close()
    print("Database cleaned and vacuumed successfully!")

    # 7. Sync cleaned database back to Google Drive
    print("\nSyncing cleaned database to Google Drive...")
    try:
        with open("google_drive_token.json", "r") as tf:
            os.environ["GOOGLE_DRIVE_OAUTH_JSON"] = tf.read()

        from storage.google_drive import GoogleDriveStorage
        gdrive = GoogleDriveStorage()
        if gdrive.enabled:
            with open(db_path, "rb") as db_f:
                cleaned_bytes = db_f.read()
            res = gdrive.upload_bytes(category="database", thread_id="system", filename="chatbot.db", file_bytes=cleaned_bytes)
            print(f"Clean database synced to Google Drive: {res.get('file_id')}")
        else:
            print("Google Drive storage disabled or not authorized.")
    except Exception as exc:
        print(f"Google Drive sync warning: {exc}")

    return archive_payload

if __name__ == "__main__":
    export_and_clean_conversations()
