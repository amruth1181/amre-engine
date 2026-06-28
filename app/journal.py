"""
Mistake journal + weak-topic profile (IMPLEMENTATION.md §9.6, §9.7, §10).

Per-user mistakes are logged with a topic and an error-type bucket. Aggregations
power the My-Progress dashboard ("70% of your misses are sign errors") and the
weak-topic profile that drives targeted practice.
"""
from datetime import datetime
from typing import Dict, Any, List
from collections import Counter

from . import db


def log_mistake(user_id: int, problem: str, topic: str, error_step: int,
                error_type: str, explanation: str) -> int:
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO journal (user_id, ts, problem, topic, error_step, error_type, explanation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, datetime.now().isoformat(), problem, topic, error_step, error_type, explanation),
    )
    conn.commit()
    jid = c.lastrowid
    conn.close()
    return jid


def get_journal(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT ts, problem, topic, error_step, error_type, explanation "
        "FROM journal WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def profile(user_id: int) -> Dict[str, Any]:
    """Aggregate the user's journal into topic + error-type breakdowns."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT topic, error_type FROM journal WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()

    topic_counts = Counter(r["topic"] for r in rows if r["topic"])
    error_counts = Counter(r["error_type"] for r in rows if r["error_type"])
    total = sum(error_counts.values())

    weakest_topics = [t for t, _ in topic_counts.most_common(3)]
    error_breakdown = {
        et: {"count": ct, "pct": round(100 * ct / total, 1) if total else 0.0}
        for et, ct in error_counts.most_common()
    }

    return {
        "total_mistakes": len(rows),
        "weakest_topics": weakest_topics,
        "topic_counts": dict(topic_counts),
        "error_breakdown": error_breakdown,
    }


def weakest_topic(user_id: int) -> str:
    p = profile(user_id)
    return p["weakest_topics"][0] if p["weakest_topics"] else ""
