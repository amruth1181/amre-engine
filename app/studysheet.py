"""
Study-sheet PDF export (IMPLEMENTATION.md §9.9).

Builds a per-user revision PDF from data already on the engine: the mistake
journal (problems + error types + explanations), the weak-topic / error-type
profile, curated reading material for the weak topics, and recent quiz results.

Uses fpdf2 (pure Python, no system deps) instead of weasyprint so it never
breaks the constrained free-tier build. Imported lazily so a missing dependency
can't block engine startup; the endpoint returns 503 if it's unavailable.
"""
from datetime import datetime
from typing import Optional

from . import db
from . import journal as journal_mod
from . import topics as topics_mod

_REPL = {
    "→": "->", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
    "…": "...", "≥": ">=", "≤": "<=", "×": "x", "÷": "/", "≈": "~",
    "²": "^2", "³": "^3", "√": "sqrt", "π": "pi", "•": "-", "∫": "integral",
}


def _asc(s) -> str:
    s = "" if s is None else str(s)
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _username(user_id: int) -> str:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["username"] if row else f"user {user_id}"


def _recent_quiz(user_id: int, limit: int = 10):
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT qi.question, qi.verified_answer, qi.user_answer, qi.correct, q.topic "
        "FROM quiz_item qi JOIN quiz q ON qi.quiz_id = q.quiz_id "
        "WHERE q.user_id = ? AND qi.user_answer IS NOT NULL "
        "ORDER BY qi.id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def build_study_sheet(user_id: int) -> Optional[bytes]:
    """Return the study-sheet PDF as bytes, or None if fpdf isn't available."""
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ fpdf2 unavailable, cannot build study sheet: {e}")
        return None

    username = _username(user_id)
    journal = journal_mod.get_journal(user_id, limit=50)
    profile = journal_mod.profile(user_id)
    quiz = _recent_quiz(user_id)

    class PDF(FPDF):
        def multi_cell(self, *a, **k):
            k.setdefault("new_x", XPos.LMARGIN)
            k.setdefault("new_y", YPos.NEXT)
            return super().multi_cell(*a, **k)

        def h1(self, t):
            self.set_font("Helvetica", "B", 16); self.set_text_color(30, 30, 90)
            self.multi_cell(0, 8, _asc(t)); self.set_text_color(0); self.ln(1)
            self.set_draw_color(120, 120, 180)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

        def h2(self, t):
            self.ln(1); self.set_font("Helvetica", "B", 12); self.set_text_color(40, 40, 100)
            self.multi_cell(0, 6.5, _asc(t)); self.set_text_color(0)

        def body(self, t, size=10.5):
            self.set_font("Helvetica", "", size); self.multi_cell(0, 5.4, _asc(t))

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 14, 16)
    pdf.add_page()

    # ---- header ----
    pdf.h1(f"AMRE Study Sheet - {username}")
    pdf.set_font("Helvetica", "I", 9); pdf.set_text_color(120)
    pdf.multi_cell(0, 5, _asc(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"))
    pdf.set_text_color(0); pdf.ln(2)

    # ---- summary ----
    pdf.h2("Summary")
    weak = profile.get("weakest_topics") or []
    pdf.body(f"Total mistakes logged: {profile.get('total_mistakes', 0)}")
    pdf.body("Weakest topics: " + (", ".join(topics_mod.pretty(t) for t in weak) if weak else "none yet"))
    eb = profile.get("error_breakdown", {})
    if eb:
        line = "; ".join(f"{k}: {v['pct']:.0f}%" for k, v in eb.items())
        pdf.body(f"Error-type breakdown: {line}")
        top = max(eb.items(), key=lambda kv: kv[1]["count"])
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.multi_cell(0, 5.6, _asc(f"Focus: {top[1]['pct']:.0f}% of your misses are {top[0]} errors."))

    # ---- mistakes ----
    pdf.ln(1); pdf.h2("Your mistakes & how to fix them")
    if journal:
        for i, m in enumerate(journal, 1):
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.multi_cell(0, 5.4, _asc(f"{i}. [{topics_mod.pretty(m.get('topic') or 'general')}] "
                                       f"{m.get('problem', '')}"))
            pdf.set_font("Helvetica", "", 10)
            meta = f"   error type: {m.get('error_type', '?')}"
            if m.get("error_step"):
                meta += f" - first slip at step {m['error_step']}"
            pdf.multi_cell(0, 5.2, _asc(meta))
            if m.get("explanation"):
                pdf.set_text_color(60, 60, 60)
                pdf.multi_cell(0, 5.2, _asc(f"   {m['explanation']}"))
                pdf.set_text_color(0)
            pdf.ln(0.8)
    else:
        pdf.body("No mistakes logged yet - check some work or take a quiz to populate this.")

    # ---- reading material for weak topics ----
    if weak:
        pdf.ln(1); pdf.h2("Reading material for your weak topics")
        for t in weak:
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.multi_cell(0, 5.4, _asc(topics_mod.pretty(t)))
            pdf.body(topics_mod.mini_lesson(t), size=10)
            for r in topics_mod.get_resources(t):
                pdf.set_text_color(40, 40, 160)
                pdf.multi_cell(0, 5.0, _asc(f"   - {r['title']}: {r['url']}"))
                pdf.set_text_color(0)
            pdf.ln(0.8)

    # ---- recent quiz ----
    if quiz:
        pdf.ln(1); pdf.h2("Recent quiz results")
        for q in quiz:
            mark = "[correct]" if q.get("correct") else "[wrong]"
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(0, 5.2, _asc(f"{mark} {q.get('question', '')}"))
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5.0, _asc(f"   verified answer: {q.get('verified_answer', '')}"))

    return bytes(pdf.output())
