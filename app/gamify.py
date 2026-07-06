"""
Streak + XP + badges gamification (feature 2.5).

XP is awarded for correct answers; a daily-login streak rewards consistency;
milestone badges unlock at XP and streak thresholds. All state lives on the
users row (xp, streak, last_active) plus a badges table.
"""
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

from . import db

# XP thresholds -> badge
_XP_BADGES = [
    (100, "Getting Started"),
    (500, "Rising Star"),
    (1000, "Math Warrior"),
    (2500, "Grandmaster"),
]
# streak-length thresholds -> badge
_STREAK_BADGES = [
    (3, "3-Day Streak"),
    (7, "Week Warrior"),
    (30, "Monthly Master"),
]
LEVEL_XP = 100  # XP per level


def _award_badge(conn, user_id: int, badge: str) -> bool:
    """Insert a badge once. Returns True if newly awarded."""
    c = conn.cursor()
    c.execute("SELECT 1 FROM badges WHERE user_id = ? AND badge = ?", (user_id, badge))
    if c.fetchone():
        return False
    c.execute("INSERT INTO badges (user_id, badge, awarded_at) VALUES (?, ?, ?)",
              (user_id, badge, datetime.now().isoformat()))
    return True


def award_xp(user_id: int, amount: int, reason: str = "") -> Dict[str, Any]:
    """Add XP and unlock any newly-earned XP badges."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id = ?", (amount, user_id))
    c.execute("SELECT COALESCE(xp, 0) AS xp FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    xp = row["xp"] if row else 0
    awarded = [b for thr, b in _XP_BADGES if xp >= thr and _award_badge(conn, user_id, b)]
    conn.commit()
    conn.close()
    return {"xp": xp, "awarded": awarded}


def update_streak(user_id: int) -> int:
    """Advance the daily streak: +1 if last active yesterday, keep if today, else reset to 1."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(streak, 0) AS streak, last_active FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    today = date.today().isoformat()
    streak = (row["streak"] if row else 0) or 0
    last_day = (row["last_active"] or "")[:10] if row else ""

    if last_day == today:
        pass  # already counted today
    elif last_day == (date.today() - timedelta(days=1)).isoformat():
        streak += 1
    else:
        streak = 1

    c.execute("UPDATE users SET streak = ?, last_active = ? WHERE user_id = ?", (streak, today, user_id))
    for thr, b in _STREAK_BADGES:
        if streak >= thr:
            _award_badge(conn, user_id, b)
    conn.commit()
    conn.close()
    return streak


def stats(user_id: int) -> Dict[str, Any]:
    """Current gamification state for the profile/home banner."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(xp, 0) AS xp, COALESCE(streak, 0) AS streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    xp = row["xp"] if row else 0
    streak = row["streak"] if row else 0
    c.execute("SELECT badge, awarded_at FROM badges WHERE user_id = ? ORDER BY id", (user_id,))
    badges: List[Dict[str, Any]] = [dict(r) for r in c.fetchall()]
    conn.close()
    level = xp // LEVEL_XP
    into = xp % LEVEL_XP
    return {
        "xp": xp,
        "level": level,
        "xp_into_level": into,
        "xp_to_next": LEVEL_XP - into,
        "streak": streak,
        "badges": badges,
    }
