"""Reconciliation script to replay unprojected events and repair sequence gaps."""
from __future__ import annotations

import argparse
import os
import sys

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.auth.database import get_db_connection
from src.harness.store import append_harness_event, get_harness_events, get_harness_session


def reconcile_threads(thread_id: str | None = None, dry_run: bool = False, db_path: str | None = None) -> int:
    print(f"=== Harness Reconciliation (dry_run={dry_run}) ===")
    repaired_count = 0

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if thread_id:
            cursor.execute("SELECT thread_id, user_id, last_event_seq FROM harness_sessions WHERE thread_id = ?", (thread_id,))
        else:
            cursor.execute("SELECT thread_id, user_id, last_event_seq FROM harness_sessions")
        sessions = cursor.fetchall()

    for row in sessions:
        tid = row["thread_id"]
        last_seq = row["last_event_seq"]
        events = get_harness_events(tid, db_path=db_path)
        if not events:
            continue

        max_seq = max(e["seq"] for e in events)
        if max_seq > last_seq:
            print(f"[Thread {tid}] Gap detected: recorded last_seq={last_seq}, actual max_seq={max_seq}")
            if not dry_run:
                with get_db_connection(db_path) as conn:
                    conn.cursor().execute(
                        "UPDATE harness_sessions SET last_event_seq = ?, updated_at = CURRENT_TIMESTAMP WHERE thread_id = ?",
                        (max_seq, tid),
                    )
                    conn.commit()
            repaired_count += 1

        # Check for unprojected assistant messages
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM messages WHERE thread_id = ?", (tid,))
            existing_msg_ids = {r["id"] for r in cursor.fetchall()}

        for e in events:
            if e["event_type"] == "assistant/message":
                proj_id = f"proj-{tid}-{e['seq']}"
                if proj_id not in existing_msg_ids:
                    print(f"[Thread {tid}] Missing projected message at seq={e['seq']}")
                    if not dry_run:
                        append_harness_event(
                            thread_id=tid,
                            seq=e["seq"],
                            event_type=e["event_type"],
                            payload=e["payload"],
                            db_path=db_path,
                        )
                    repaired_count += 1

    print(f"=== Completed. Repaired {repaired_count} inconsistencies. ===")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness persistence reconciliation tool")
    parser.add_argument("--thread-id", type=str, help="Specific thread ID to reconcile")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying database")
    parser.add_argument("--db-path", type=str, help="Custom SQLite database path")
    args = parser.parse_args()

    sys.exit(reconcile_threads(thread_id=args.thread_id, dry_run=args.dry_run, db_path=args.db_path))


if __name__ == "__main__":
    main()

