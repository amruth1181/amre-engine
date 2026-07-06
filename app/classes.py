"""
Teacher / Class layer (feature 1.3) — makes AMRE sellable to schools.

Teachers create classes with a shareable join code; students join; the teacher
sees aggregate weak topics and a per-student breakdown, and can assign topic
quizzes. Ownership is enforced on every teacher-only operation.
"""
import random
import string
from collections import Counter
from datetime import datetime
from typing import Dict, Any

from . import db
from . import journal as journal_mod
from . import topics as topics_mod


def _gen_code(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def role_of(user_id: int) -> str:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return (row["role"] if row and row["role"] else "student")


def become_teacher(user_id: int) -> None:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET role = 'teacher' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_class(teacher_id: int, name: str) -> Dict[str, Any]:
    become_teacher(teacher_id)  # creating a class makes you a teacher
    conn = db.get_db()
    c = conn.cursor()
    code = _gen_code()
    for _ in range(10):  # ensure uniqueness
        c.execute("SELECT 1 FROM classes WHERE join_code = ?", (code,))
        if not c.fetchone():
            break
        code = _gen_code()
    c.execute("INSERT INTO classes (teacher_id, name, join_code, created_at) VALUES (?, ?, ?, ?)",
              (teacher_id, name.strip() or "Untitled class", code, datetime.now().isoformat()))
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return {"class_id": cid, "name": name, "join_code": code}


def join_class(user_id: int, join_code: str) -> Dict[str, Any]:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT class_id, name FROM classes WHERE join_code = ?", (join_code.strip().upper(),))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": "No class with that code."}
    cid = row["class_id"]
    c.execute("SELECT 1 FROM class_members WHERE class_id = ? AND user_id = ?", (cid, user_id))
    if not c.fetchone():
        c.execute("INSERT INTO class_members (class_id, user_id, joined_at) VALUES (?, ?, ?)",
                  (cid, user_id, datetime.now().isoformat()))
        conn.commit()
    conn.close()
    return {"class_id": cid, "name": row["name"]}


def list_classes(user_id: int) -> Dict[str, Any]:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT class_id, name, join_code FROM classes WHERE teacher_id = ? ORDER BY class_id DESC",
              (user_id,))
    teaching = [dict(r) for r in c.fetchall()]
    c.execute("SELECT cl.class_id, cl.name FROM classes cl "
              "JOIN class_members m ON cl.class_id = m.class_id "
              "WHERE m.user_id = ? ORDER BY cl.class_id DESC", (user_id,))
    enrolled = [dict(r) for r in c.fetchall()]
    for e in enrolled:
        c.execute("SELECT topic, title FROM assignments WHERE class_id = ? ORDER BY id DESC", (e["class_id"],))
        e["assignments"] = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"role": role_of(user_id), "teaching": teaching, "enrolled": enrolled}


def dashboard(teacher_id: int, class_id: int) -> Dict[str, Any]:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM classes WHERE class_id = ? AND teacher_id = ?", (class_id, teacher_id))
    cls = c.fetchone()
    if not cls:
        conn.close()
        return {"error": "Not your class (or it doesn't exist)."}
    c.execute("SELECT m.user_id, u.username FROM class_members m "
              "JOIN users u ON m.user_id = u.user_id WHERE m.class_id = ?", (class_id,))
    members = [dict(r) for r in c.fetchall()]
    c.execute("SELECT topic, title, created_at FROM assignments WHERE class_id = ? ORDER BY id DESC", (class_id,))
    assignments = [dict(r) for r in c.fetchall()]
    conn.close()

    class_topic_counts: Counter = Counter()
    students = []
    for m in members:
        prof = journal_mod.profile(m["user_id"])
        for t, ct in prof.get("topic_counts", {}).items():
            class_topic_counts[t] += ct
        weak = prof.get("weakest_topics", [])
        students.append({
            "username": m["username"],
            "mistakes": prof.get("total_mistakes", 0),
            "weakest_topic": topics_mod.pretty(weak[0]) if weak else "—",
        })

    return {
        "class_name": cls["name"],
        "student_count": len(members),
        "class_weak_topics": {topics_mod.pretty(t): ct for t, ct in class_topic_counts.most_common(8)},
        "students": students,
        "assignments": assignments,
    }


def assign(teacher_id: int, class_id: int, topic: str, title: str = "") -> Dict[str, Any]:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM classes WHERE class_id = ? AND teacher_id = ?", (class_id, teacher_id))
    if not c.fetchone():
        conn.close()
        return {"error": "Not your class."}
    c.execute("INSERT INTO assignments (class_id, topic, title, created_at) VALUES (?, ?, ?, ?)",
              (class_id, topic, title or topics_mod.pretty(topic), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}
