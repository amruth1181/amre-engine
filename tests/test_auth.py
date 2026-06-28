"""Auth + per-user data isolation (IMPLEMENTATION.md §3.9, §6)."""
import pytest
from fastapi import HTTPException

from app import auth, db, journal as journal_mod


def test_register_and_login_roundtrip():
    out = auth.register(auth.UserCreate(username="alice", password="pw"))
    assert out["user_id"] and out["token"]
    login = auth.login(auth.UserLogin(username="alice", password="pw"))
    assert login["user_id"] == out["user_id"]


def test_duplicate_username_rejected():
    auth.register(auth.UserCreate(username="bob", password="pw"))
    with pytest.raises(HTTPException):
        auth.register(auth.UserCreate(username="bob", password="other"))


def test_wrong_password_rejected():
    auth.register(auth.UserCreate(username="carol", password="right"))
    with pytest.raises(HTTPException):
        auth.login(auth.UserLogin(username="carol", password="wrong"))


def test_token_roundtrip_and_require_user():
    out = auth.register(auth.UserCreate(username="dave", password="pw"))
    assert auth.decode_token(out["token"]) == out["user_id"]
    assert auth.require_user(f"Bearer {out['token']}") == out["user_id"]


def test_require_user_rejects_missing_and_bad_tokens():
    with pytest.raises(HTTPException):
        auth.require_user(None)
    with pytest.raises(HTTPException):
        auth.require_user("Bearer not-a-real-token")


def test_two_users_journals_are_isolated():
    u1 = auth.register(auth.UserCreate(username="u1", password="pw"))["user_id"]
    u2 = auth.register(auth.UserCreate(username="u2", password="pw"))["user_id"]

    journal_mod.log_mistake(u1, "p1", "linear_equations", 1, "sign", "x1")
    journal_mod.log_mistake(u1, "p2", "quadratics", 2, "concept", "x2")
    journal_mod.log_mistake(u2, "p3", "probability", 1, "concept", "x3")

    j1 = journal_mod.get_journal(u1)
    j2 = journal_mod.get_journal(u2)
    assert len(j1) == 2 and len(j2) == 1
    assert all(r["problem"] != "p3" for r in j1)          # u1 never sees u2's mistake
    assert journal_mod.weakest_topic(u2) == "probability"
