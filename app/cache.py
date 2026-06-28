"""
Lightweight in-process response cache (IMPLEMENTATION.md §0 / §7).
Cuts duplicate provider calls (a solve at N=32 ≈ 32 calls). Keyed by
problem_hash + mode. In-memory LRU is enough for a single-process engine;
SQLite-backed caching is a backlog item.
"""
from collections import OrderedDict
from typing import Any, Optional
import threading

_MAX = 256
_store: "OrderedDict[str, Any]" = OrderedDict()
_lock = threading.Lock()


def _key(problem_hash: str, mode: str) -> str:
    return f"{mode}:{problem_hash}"


def get(problem_hash: str, mode: str) -> Optional[Any]:
    k = _key(problem_hash, mode)
    with _lock:
        if k in _store:
            _store.move_to_end(k)
            return _store[k]
    return None


def put(problem_hash: str, mode: str, value: Any) -> None:
    k = _key(problem_hash, mode)
    with _lock:
        _store[k] = value
        _store.move_to_end(k)
        while len(_store) > _MAX:
            _store.popitem(last=False)


def clear() -> None:
    with _lock:
        _store.clear()
