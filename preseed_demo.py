"""
preseed_demo.py (IMPLEMENTATION.md §3.9 / §5).

Creates demo accounts with pre-populated history + mistake journal so the
My-Progress dashboard and weak-topic profile look alive on Day 1 of the pitch.
Writes straight to SQLite (no API/provider calls needed).

Usage:  python preseed_demo.py
Demo logins printed at the end.
"""
from datetime import datetime, timedelta
import random

import db
import auth
import topics as topics_mod

DEMO_USERS = [
    ("demo_alice", "password123"),
    ("demo_bob", "password123"),
]

SOLVED = [
    ("Solve for x: 2x + 5 = 15", "5", "auto", "prm_weighted_vote", 8, 0.91),
    ("What is 25% of 80?", "20", "fast", "greedy", 1, 0.97),
    ("Factor: x^2 + 5x + 6", "(x+2)(x+3)", "auto", "prm_weighted_vote", 8, 0.84),
    ("Solve for x: x^2 - 9 = 0", "3 or -3", "careful", "prm_weighted_vote", 16, 0.88),
    ("Simplify: (2/3) + (1/6)", "5/6", "auto", "prm_weighted_vote", 8, 0.79),
    ("A bag has 3 red and 2 blue balls. P(red)?", "3/5", "auto", "prm_weighted_vote", 16, 0.72),
    ("Find the area of a circle with radius 4.", "16pi", "balanced", "prm_weighted_vote", 8, 0.9),
]

MISTAKES = [
    ("Solve for x: -3x = 12", "linear_equations", 2, "sign", "Dropped the negative when dividing; x should be -4, not 4."),
    ("Solve for x: x^2 - 9 = 0", "quadratics", 1, "concept", "Took only the positive root; remember ± for x²."),
    ("Solve for x: -2x + 4 = 10", "linear_equations", 2, "sign", "Sign error moving +4 across the equals sign."),
    ("A bag has 3 red and 2 blue balls. P(red)?", "probability", 1, "concept", "Used total favorable over favorable instead of over total."),
    ("Simplify: (2/3) + (1/6)", "fractions_ratios", 2, "arithmetic", "Added denominators instead of finding a common one."),
]


def seed_user(username, password):
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if row:
        user_id = row["user_id"]
        print(f"• {username} already exists (user_id={user_id}) — refreshing demo data")
        c.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM journal WHERE user_id = ?", (user_id,))
    else:
        c.execute("INSERT INTO users (username, pw_hash) VALUES (?, ?)",
                  (username, auth.hash_password(password)))
        user_id = c.lastrowid
        print(f"• created {username} (user_id={user_id})")

    now = datetime.now()
    for i, (problem, answer, mode, route, n, conf) in enumerate(SOLVED):
        ts = (now - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))).isoformat()
        c.execute(
            "INSERT INTO history (user_id, ts, problem, problem_hash, mode, route, n_used, escalated, answer, confidence, latency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, ts, problem, db.problem_hash(problem), mode, route, n, 0, answer, conf,
             round(random.uniform(800, 4000), 1)),
        )
    for problem, topic, err_step, err_type, expl in MISTAKES:
        ts = (now - timedelta(days=random.randint(0, 6))).isoformat()
        c.execute(
            "INSERT INTO journal (user_id, ts, problem, topic, error_step, error_type, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, ts, problem, topic, err_step, err_type, expl),
        )

    conn.commit()
    conn.close()


def main():
    db.init_db()
    for username, password in DEMO_USERS:
        seed_user(username, password)
    print("\n✅ Demo data seeded. Logins:")
    for u, p in DEMO_USERS:
        print(f"   {u} / {p}")


if __name__ == "__main__":
    main()
