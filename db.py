"""
Central SQLite persistence (IMPLEMENTATION.md §3.10).
All per-user data lives here on the engine's persistent disk.

Tables:
  users(user_id, username, pw_hash, created_at)
  history(id, user_id, ts, problem, problem_hash, mode, route, n_used, escalated, answer, confidence, latency)
  journal(id, user_id, ts, problem, topic, error_step, error_type, explanation)
  quiz(quiz_id, user_id, topic, ts)
  quiz_item(id, quiz_id, question, verified_answer, user_answer, correct)
  selfrate(id, user_id, item_id, user_conf, model_conf, correct)
"""
import os
import sqlite3
import hashlib

DB_PATH = os.environ.get("DB_PATH", "/data/amre.db" if os.path.isdir("/data") else "./amre.db")


def problem_hash(problem: str) -> str:
    return hashlib.sha256(problem.strip().lower().encode()).hexdigest()[:16]


def get_db():
    """Open a connection with row factory. Caller is responsible for closing."""
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they do not exist. Idempotent — safe at every startup."""
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            problem TEXT,
            problem_hash TEXT,
            mode TEXT,
            route TEXT,
            n_used INTEGER,
            escalated INTEGER DEFAULT 0,
            answer TEXT,
            confidence REAL,
            latency REAL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            problem TEXT,
            topic TEXT,
            error_step INTEGER,
            error_type TEXT,
            explanation TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS quiz (
            quiz_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT,
            ts TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS quiz_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            question TEXT,
            verified_answer TEXT,
            user_answer TEXT,
            correct INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS selfrate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT,
            user_conf REAL,
            model_conf REAL,
            correct INTEGER,
            ts TEXT
        )
    ''')

    conn.commit()
    conn.close()


# ---- migration helper: older DBs used users(id, password_hash) ----
def _has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == col for row in cur.fetchall())


def migrate_legacy():
    """Best-effort migration from the early schema (users.id / password_hash,
    history without the newer columns). Silently no-ops on a fresh DB."""
    conn = get_db()
    try:
        # users: legacy column "id" / "password_hash"
        if _has_column(conn, "users", "id") and not _has_column(conn, "users", "user_id"):
            # SQLite can't rename a PK column cleanly across versions; rebuild.
            conn.executescript('''
                ALTER TABLE users RENAME TO users_legacy;
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    pw_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO users (user_id, username, pw_hash, created_at)
                    SELECT id, username, password_hash, created_at FROM users_legacy;
                DROP TABLE users_legacy;
            ''')
        # history: add any missing newer columns
        for col, ddl in [
            ("ts", "ALTER TABLE history ADD COLUMN ts TEXT"),
            ("problem_hash", "ALTER TABLE history ADD COLUMN problem_hash TEXT"),
            ("route", "ALTER TABLE history ADD COLUMN route TEXT"),
            ("escalated", "ALTER TABLE history ADD COLUMN escalated INTEGER DEFAULT 0"),
            ("latency", "ALTER TABLE history ADD COLUMN latency REAL"),
        ]:
            if _has_column(conn, "history", "timestamp") and not _has_column(conn, "history", col):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
