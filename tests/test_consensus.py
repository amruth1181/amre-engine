"""Answer normalization + PRM-weighted voting (IMPLEMENTATION.md §3.5, §6)."""
from app import consensus


def test_normalize_strips_units_and_currency():
    assert consensus.normalize_answer("$15") == "15"
    assert consensus.normalize_answer("5 kg") == "5"


def test_normalize_fraction_equivalence():
    # 2/3 and its decimal collapse to the same key
    assert consensus.normalize_answer("2/3") == consensus.normalize_answer("0.6667")


def test_normalize_integer_float():
    assert consensus.normalize_answer("5.0") == "5"
    assert consensus.normalize_answer("x = 5") == "5"


def test_weighted_vote_picks_highest_weight_group():
    chains = [
        {"answer": "5", "scores": [0.9, 0.8]},   # min weight 0.8
        {"answer": "5", "scores": [0.7]},        # min weight 0.7  -> group "5" = 1.5
        {"answer": "4", "scores": [0.6]},        # group "4" = 0.6
    ]
    best, agreement, tally = consensus.run_consensus(chains)
    assert consensus.normalize_answer(best) == "5"
    assert tally["5"] > tally["4"]
    assert 0.0 <= agreement <= 1.0


def test_empty_chains_safe_default():
    best, agreement, tally = consensus.run_consensus([])
    assert tally == {}
    assert 0.0 <= agreement <= 1.0
