"""Segmentation + answer extraction (IMPLEMENTATION.md §3.2, §6)."""
from app import segment


def test_numbered_steps():
    text = "Step 1: a = 2.\nStep 2: b = 3.\nFinal Answer: 5"
    steps = segment.segment_steps(text)
    assert steps == ["a = 2.", "b = 3."]


def test_final_answer_stripped_from_last_step():
    text = "Step 1: combine.\nStep 2: result is 7. Final Answer: 7"
    steps = segment.segment_steps(text)
    assert all("Final Answer" not in s for s in steps)


def test_fallback_on_unnumbered_text():
    # user-pasted prose without "Step k:" still yields non-empty steps
    text = "first we move terms\nthen we divide\nso x is 4"
    steps = segment.segment_steps(text)
    assert len(steps) >= 1


def test_extract_answer_explicit():
    assert segment.extract_answer("blah\nFinal Answer: 42") == "42"


def test_extract_answer_case_insensitive():
    assert segment.extract_answer("final answer: -3") == "-3"


def test_extract_answer_strips_x_equals():
    assert segment.extract_answer("x = 9") == "9"
