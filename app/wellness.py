"""
Weekly wellness summary + in-app alerts (additive, read-only).

Aggregates the last 7 days of activity from the existing history/journal tables
(plus gamify + review) and asks the LLM for a short, supportive coach-style note.
No new tables, no schema changes — pure reads. Degrades to a templated summary
when the LLM is unavailable, so the endpoint never fails.
"""
from datetime import datetime, timedelta, date
from collections import Counter
from typing import Dict, Any

from . import db
from . import gamify
from . import journal as journal_mod
from . import generate

_COACH_SYSTEM = (
    "You are a warm, encouraging study coach for a high-school math student. "
    "Given the student's weekly activity stats, write 2-3 short sentences of "
    "supportive feedback. Celebrate effort and consistency, mention their "
    "strongest day and streak when present, and gently encourage them to keep "
    "going. This is a friendly check-in, NOT a grade or a judgment. Do not invent "
    "any numbers beyond those given. Keep it under 60 words."
)


def _weekday(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%A")
    except Exception:  # noqa: BLE001
        return ""


def weekly_stats(user_id: int) -> Dict[str, Any]:
    """Read-only aggregation of the last 7 days from history + journal (+ review)."""
    since = (datetime.now() - timedelta(days=7)).isoformat()
    today = date.today().isoformat()
    conn = db.get_db()
    c = conn.cursor()

    c.execute("SELECT ts FROM history WHERE user_id = ? AND ts >= ?", (user_id, since))
    solve_days = [str(r["ts"])[:10] for r in c.fetchall()]

    c.execute("SELECT ts FROM journal WHERE user_id = ? AND ts >= ?", (user_id, since))
    mistake_days = [str(r["ts"])[:10] for r in c.fetchall()]

    c.execute(
        "SELECT COUNT(*) AS n FROM review "
        "WHERE user_id = ? AND due_date IS NOT NULL AND due_date <= ?",
        (user_id, today),
    )
    row = c.fetchone()
    cards_due = (row["n"] if row else 0) or 0
    conn.close()

    problems_solved = len(solve_days)
    mistakes_caught = len(mistake_days)
    active_days = set(solve_days) | set(mistake_days)
    day_counts = Counter(solve_days)
    strongest_iso = day_counts.most_common(1)[0][0] if day_counts else ""

    g = gamify.stats(user_id)
    weakest = journal_mod.profile(user_id).get("weakest_topics") or []
    top_topic = weakest[0].replace("_", " ").title() if weakest else ""

    return {
        "days_studied": len(active_days),
        "problems_solved": problems_solved,
        "mistakes_caught": mistakes_caught,
        "strongest_day": _weekday(strongest_iso),
        "top_topic": top_topic,
        "cards_due": cards_due,
        "streak": g.get("streak", 0),
        "xp": g.get("xp", 0),
        "level": g.get("level", 0),
    }


def _fallback_summary(s: Dict[str, Any]) -> str:
    """Deterministic coach note used when the LLM is unavailable."""
    if s["days_studied"] == 0:
        return ("Fresh start! You haven't logged any practice this week yet — solve a "
                "problem or check your work to get your streak going. Every expert "
                "started with a single step. 💪")
    text = (f"This week you studied {s['days_studied']} day(s) and worked "
            f"{s['problems_solved']} problem(s)")
    if s["mistakes_caught"]:
        text += f", catching and reviewing {s['mistakes_caught']} mistake(s)"
    text += "."
    if s["strongest_day"]:
        text += f" Your strongest day was {s['strongest_day']}."
    text += (f" You're on a {s['streak']}-day streak — keep it alive! 🔥"
             if s["streak"] else " Keep up the great work!")
    return text


async def build_summary(user_id: int) -> Dict[str, Any]:
    """Full payload for the Weekly Summary page: coach note + stats + alerts."""
    s = weekly_stats(user_id)
    prompt = (
        "Weekly stats for the student:\n"
        f"- Days studied this week: {s['days_studied']}\n"
        f"- Problems worked: {s['problems_solved']}\n"
        f"- Mistakes caught and reviewed: {s['mistakes_caught']}\n"
        f"- Strongest day: {s['strongest_day'] or 'n/a'}\n"
        f"- Current day-streak: {s['streak']}\n"
        f"- Topic to focus on next: {s['top_topic'] or 'n/a'}\n"
        "Write the supportive weekly check-in now."
    )
    text = await generate.generate_text(prompt, system=_COACH_SYSTEM,
                                        max_tokens=160, temperature=0.7)
    summary = text.strip() if text else _fallback_summary(s)

    return {
        "summary": summary,
        "stats": {
            "days_studied": s["days_studied"],
            "problems_solved": s["problems_solved"],
            "mistakes_caught": s["mistakes_caught"],
            "strongest_day": s["strongest_day"],
            "top_topic": s["top_topic"],
        },
        "alerts": {
            "cards_due": s["cards_due"],
            "streak": s["streak"],
            "xp": s["xp"],
            "level": s["level"],
        },
    }
