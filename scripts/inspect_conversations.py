import sqlite3
import json

conn = sqlite3.connect('chatbot_gdrive.db')
c = conn.cursor()

c.execute('SELECT id, email, full_name, role FROM users')
users = {u[0]: {'email': u[1], 'name': u[2], 'role': u[3]} for u in c.fetchall()}

c.execute('SELECT id, user_id, title, updated_at FROM threads ORDER BY user_id, updated_at DESC')
threads = c.fetchall()

print(f'Total threads in database: {len(threads)}')
by_user = {}
for tid, uid, title, updated in threads:
    by_user.setdefault(uid, []).append((tid, title, updated))

for uid, tlist in by_user.items():
    uinfo = users.get(uid, {'email': 'Unknown', 'name': 'Unknown'})
    print(f'\n======================================================================')
    print(f'USER: {uinfo["name"]} ({uinfo["email"]})')
    print(f'USER ID: {uid}')
    print(f'Total Conversations: {len(tlist)}')
    print(f'======================================================================')
    for tid, title, updated in tlist:
        # Check messages table
        c.execute('SELECT role, content FROM messages WHERE thread_id = ? ORDER BY timestamp ASC', (tid,))
        msgs = c.fetchall()
        print(f'\n  [Thread ID: {tid}]')
        print(f'  Title: {title}')
        print(f'  Last Updated: {updated}')
        if msgs:
            for role, content in msgs:
                snippet = (content[:100] + '...') if len(content) > 100 else content
                snippet = snippet.replace('\n', ' ')
                print(f'    -> {role.upper()}: {snippet}')
        else:
            # Let's check checkpoints if messages table is empty
            c.execute('SELECT checkpoint FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1', (tid,))
            cp_row = c.fetchone()
            if cp_row and cp_row[0]:
                try:
                    cp_data = json.loads(cp_row[0]) if isinstance(cp_row[0], str) else cp_row[0]
                    # checkpoint might be pickle or json
                    print(f'    (Stored in LangGraph checkpoint)')
                except Exception:
                    print(f'    (Checkpoint binary blob)')
