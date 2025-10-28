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
            offset INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            last_send_ts INTEGER DEFAULT 0,
            ai_template  TEXT,
            ai_template_es  TEXT,
            ai_template_en TEXT
        )
    """)

    # 🔍 Verifica si la columna total_likes existe en post_progress
    cur.execute("PRAGMA table_info(post_progress)")
    columns = [row[1] for row in cur.fetchall()]
    if "total_likes" not in columns:
        print("⚙️ Actualizando base de datos: agregando columna 'total_likes'...")
        cur.execute("ALTER TABLE post_progress ADD COLUMN total_likes INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Columna 'total_likes' añadida correctamente.")

    # 🔍 Verifica si la columna last_send_ts existe
    cur.execute("PRAGMA table_info(post_progress)")
    columns = [row[1] for row in cur.fetchall()]
    if "last_send_ts" not in columns:
        print("⚙️ Agregando columna 'last_send_ts'...")
        cur.execute("ALTER TABLE post_progress ADD COLUMN last_send_ts INTEGER DEFAULT 0")
        conn.commit()

    # 🔍 Verifica si la columna ai_template existe
    cur.execute("PRAGMA table_info(post_progress)")
    columns = [row[1] for row in cur.fetchall()]
    if "ai_template" not in columns:
        print("⚙️ Agregando columna 'ai_template'...")
        cur.execute("ALTER TABLE post_progress ADD COLUMN ai_template TEXT DEFAULT ''")
        conn.commit()

    if "ai_template_es" not in columns:
        print("⚙️ Agregando columna 'ai_template_es'...")
        cur.execute("ALTER TABLE post_progress ADD COLUMN ai_template_es TEXT DEFAULT ''")
        conn.commit()

    if "ai_template_en" not in columns:
        print("⚙️ Agregando columna 'ai_template_en'...")
        cur.execute("ALTER TABLE post_progress ADD COLUMN ai_template_en TEXT DEFAULT ''")
        conn.commit()

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
    cur.execute("SELECT offset, total_likes FROM post_progress WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0, 0
    return row[0], row[1]  # offset, total_likes


def save_post_progress(url, offset, total_likes):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO post_progress (url, offset, total_likes)
        VALUES (?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET offset=excluded.offset, total_likes=excluded.total_likes
    """, (url, offset, total_likes))
    conn.commit()
    conn.close()

def get_last_send_ts(url):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT last_send_ts FROM post_progress WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def update_last_send_ts(url):
    conn = db()
    cur = conn.cursor()
    ts = int(time.time())
    cur.execute("""
        INSERT INTO post_progress (url, last_send_ts)
        VALUES (?, ?)
        ON CONFLICT(url) DO UPDATE SET last_send_ts=excluded.last_send_ts
    """, (url, ts))
    conn.commit()
    conn.close()

def get_ai_templates():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT ai_template_es, ai_template_en FROM post_progress WHERE url='global_config'")
    row = cur.fetchone()
    conn.close()
    if not row:
        return "", ""
    return row[0] or "", row[1] or ""

def save_ai_templates(template_es, template_en):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO post_progress (url, ai_template_es, ai_template_en)
        VALUES ('global_config', ?, ?)
        ON CONFLICT(url) DO UPDATE
        SET ai_template_es=excluded.ai_template_es,
            ai_template_en=excluded.ai_template_en
    """, (template_es, template_en))
    conn.commit()
    conn.close()
