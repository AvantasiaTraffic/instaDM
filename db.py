import sqlite3
import time

def db():
    return sqlite3.connect("insta_bot.sqlite", check_same_thread=False)

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pk INTEGER,
            username TEXT UNIQUE,
            full_name TEXT,
            is_private INTEGER,
            contacted INTEGER DEFAULT 0,
            last_contact_ts INTEGER,
            language TEXT
        )
    """)
    # 👇 Nueva tabla de progreso reutilizando la BD
    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_progress(
            url TEXT PRIMARY KEY,
            offset INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def save_likers(likers):
    conn = db()
    cur = conn.cursor()
    added = 0
    for u in likers:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO contacts(pk, username, full_name, is_private, language)
                VALUES (?, ?, ?, ?, ?)
            """, (u["pk"], u["username"], u["full_name"], int(u["is_private"]), u.get("language", "es")))
            added += cur.rowcount
        except Exception as e:
            print(f"⚠️ Error al guardar usuario {u['username']}: {e}")
            pass
    conn.commit()
    conn.close()
    return added

def get_pending(limit=20, only_public=False):
    conn = db()
    cur = conn.cursor()
    if only_public:
        cur.execute(
            "SELECT username, full_name, pk FROM contacts WHERE contacted=0 AND is_private=0 LIMIT ?",
            (limit,),
        )
    else:
        cur.execute(
            "SELECT username, full_name, pk FROM contacts WHERE contacted=0 LIMIT ?",
            (limit,),
        )
    users = cur.fetchall()
    conn.close()
    return users

def mark_contacted(username):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contacts SET contacted = 1, last_contact_ts = ? WHERE username = ?",
        (int(time.time()), username),
    )
    conn.commit()
    conn.close()

def get_post_progress(url):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT offset FROM post_progress WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def save_post_progress(url, offset):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO post_progress (url, offset)
        VALUES (?, ?)
        ON CONFLICT(url) DO UPDATE SET offset=excluded.offset
    """, (url, offset))
    conn.commit()
    conn.close()