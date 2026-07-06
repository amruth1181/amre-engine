"""
Spaced repetition over the mistake journal (feature 1.1), using the SM-2 algorithm.

Each missed problem becomes a review card. When the student reviews it they rate
recall quality (0-5); SM-2 updates the ease factor and schedules the next review,
so weak problems resurface at expanding, scientifically-timed intervals.
"""
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

from . import db


def seed_card(user_id: int, problem: str, topic: str, source_journal_id: Optional[int] = None) -> None:
    """Create a review card for a missed problem (once per user+problem), due tomorrow."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM review WHERE user_id = ? AND problem = ?", (user_id, problem))
    if c.fetchone():
        conn.close()
        return
    due = date.today().isoformat()  # due immediately so a fresh mistake is reviewable right away
    c.execute(
        "INSERT INTO review (user_id, problem, topic, ease_factor, interval, repetitions, due_date, source_journal_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, problem, topic, 2.5, 0, 0, due, source_journal_id),
    )
    conn.commit()
    conn.close()


def due_cards(user_id: int) -> List[Dict[str, Any]]:
    """Cards due today or overdue, soonest first."""
    conn = db.get_db()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute(
        "SELECT id, problem, topic, interval, repetitions, ease_factor, due_date "
        "FROM review WHERE user_id = ? AND (due_date IS NULL OR due_date <= ?) ORDER BY due_date",
        (user_id, today),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def grade(user_id: int, card_id: int, quality: int) -> Dict[str, Any]:
    """Apply SM-2 with recall quality 0..5 and reschedule the card."""
    quality = max(0, min(5, int(quality)))
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT ease_factor, interval, repetitions FROM review WHERE id = ? AND user_id = ?",
              (card_id, user_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": "card not found"}

    ef = row["ease_factor"] or 2.5
    interval = row["interval"] or 0
    reps = row["repetitions"] or 0

    if quality < 3:
        # failed recall -> restart the interval
        reps = 0
        interval = 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = max(1, round(interval * ef))
        # SM-2 ease-factor update, floored at 1.3
        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ef = max(1.3, ef)

    due = (date.today() + timedelta(days=interval)).isoformat()
    c.execute(
        "UPDATE review SET ease_factor = ?, interval = ?, repetitions = ?, due_date = ?, last_reviewed = ? "
        "WHERE id = ?",
        (ef, interval, reps, due, datetime.now().isoformat(), card_id),
    )
    conn.commit()
    conn.close()
    return {"card_id": card_id, "interval": interval, "repetitions": reps,
            "ease_factor": round(ef, 2), "due_date": due}
