"""Router precedence + escalation flags (IMPLEMENTATION.md §3.4, §6)."""
from app import router


def test_manual_modes_win_on_budget():
    assert router.route("anything", "fast").n == 1
    assert router.route("anything", "balanced").n == 8
    assert router.route("anything", "careful").n == 32


def test_manual_modes_do_not_escalate():
    # manual modes only advise; never silently escalate
    assert router.route("anything", "balanced").escalatable is False
    assert router.route("anything", "careful").escalatable is False


def test_fast_mode_carries_advisory():
    assert router.route("anything", "fast").advisory


def test_auto_easy_is_greedy():
    r = router.route("What is 25% of 80?", "auto")
    assert r.strategy == "greedy" and r.n == 1


def test_auto_hard_is_capped_and_escalatable():
    hard = "Prove the integral of x^2 using probability and combinatorics " * 4
    r = router.route(hard, "auto")
    assert r.strategy == "prm_weighted_vote"
    assert r.n <= router.N_CAP_FREE
    assert r.escalatable is True


def test_difficulty_buckets():
    assert router.difficulty("2+2") == "easy"
    assert router.difficulty("Find the derivative of x^2 with respect to x") == "hard"
