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

# Turso / libSQL: free hosted SQLite so data survives HF Space restarts (the free
# Space has no persistent disk, so a plain /data/amre.db is wiped on every reboot).
# Set both to enable; otherwise we fall back to local sqlite3 (dev / no creds).
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()


# ---- libSQL <-> sqlite3 compatibility shim -------------------------------------
# libsql-experimental returns plain tuples and has no row_factory, but the rest of
# the codebase relies on sqlite3.Row semantics (row["col"], dict(row)). These thin
# wrappers make a libSQL connection behave like a sqlite3 one, so no caller changes.
class _Row(dict):
    """dict with positional access too, so it stands in for sqlite3.Row."""
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        self._raw.execute(sql, params) if params else self._raw.execute(sql)
        return self

    def executemany(self, sql, seq):
        self._raw.executemany(sql, seq)
        return self

    def _cols(self):
        desc = self._raw.description
        return [d[0] for d in desc] if desc else []

    def fetchone(self):
        row = self._raw.fetchone()
        return _Row(self._cols(), row) if row is not None else None

    def fetchall(self):
        cols = self._cols()
        return [_Row(cols, row) for row in self._raw.fetchall()]

    @property
    def lastrowid(self):
        return self._raw.lastrowid


class _Conn:
    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return _Cursor(self._raw.cursor())

    def execute(self, sql, params=None):
        return _Cursor(self._raw.cursor()).execute(sql, params)

    def commit(self):
        self._raw.commit()

    def close(self):
        try:
            self._raw.close()
        except Exception:  # noqa: BLE001 — remote close is best-effort
            pass


def problem_hash(problem: str) -> str:
    return hashlib.sha256(problem.strip().lower().encode()).hexdigest()[:16]


def get_db():
    """Open a connection with row factory. Caller is responsible for closing.

    Uses Turso/libSQL (persistent, survives Space restarts) when TURSO_DATABASE_URL
    is set; otherwise local sqlite3. Both expose the same sqlite3.Row-style API."""
    if TURSO_URL:
        import libsql_experimental as libsql
        return _Conn(libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN))
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

    # ---- new-feature tables (spaced repetition, classes, gamification) ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            problem TEXT,
            topic TEXT,
            ease_factor REAL DEFAULT 2.5,
            interval INTEGER DEFAULT 0,
            repetitions INTEGER DEFAULT 0,
            due_date TEXT,
            last_reviewed TEXT,
            source_journal_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            class_id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            name TEXT,
            join_code TEXT UNIQUE,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS class_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            topic TEXT,
            title TEXT,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge TEXT,
            awarded_at TEXT
        )
    ''')

    # ---- new columns on users (guarded; safe to re-run). Individual ALTERs only
    # (the Turso _Conn adapter has no executescript). ----
    for col, ddl in [
        ("role", "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'"),
        ("xp", "ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0"),
        ("streak", "ALTER TABLE users ADD COLUMN streak INTEGER DEFAULT 0"),
        ("last_active", "ALTER TABLE users ADD COLUMN last_active TEXT"),
    ]:
        if not _has_column(conn, "users", col):
            try:
                c.execute(ddl)
            except Exception:  # noqa: BLE001 — best-effort; column may already exist
                pass

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
