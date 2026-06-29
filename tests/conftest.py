"""
Shared pytest setup (IMPLEMENTATION.md §6).

Runs every test against a throwaway SQLite file and forces the offline mock
generation path (no provider key), so the suite is hermetic and needs no
network. Env vars are set BEFORE any app module is imported so module-level
path/config reads pick them up.
"""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "amre_pytest.db")
os.environ["GEMINI_API_KEY"] = ""   # force generate.py's deterministic mock bank
os.environ.setdefault("CALIBRATION_PATH", "/nonexistent/calibration.pkl")  # force identity fallback

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import db


@pytest.fixture(autouse=True)
def fresh_db():
    """Recreate the schema on a clean file before each test for isolation."""
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
    db.init_db()
    yield
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
