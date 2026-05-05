"""Small bounded helpers for optional deterministic thread parallelism."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


def normalize_parallel_mode(value: Any) -> str:
    mode = str(value or "SEQUENTIAL").strip().upper()
    return mode if mode in {"SEQUENTIAL", "THREADS"} else "SEQUENTIAL"


def normalize_max_workers(value: Any, task_count: int, *, default_limit: int = 4) -> int:
    try:
        requested = int(value) if value is not None else default_limit
    except Exception:
        requested = default_limit
    requested = max(1, requested)
    task_count = max(1, int(task_count or 1))
    return min(requested, task_count, default_limit)


def run_ordered_thread_tasks(
    items: list,
    worker: Callable[[Any], Any],
    *,
    max_workers: int | None = None,
) -> list[dict]:
    """Run independent tasks in threads and return ordered result/error records."""
    if not items:
        return []
    workers = normalize_max_workers(max_workers, len(items))

    def _safe(item: Any) -> dict:
        try:
            return {"ok": True, "result": worker(item), "error": None}
        except Exception as exc:
            return {"ok": False, "result": None, "error": exc}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_safe, items))


__all__ = ["normalize_parallel_mode", "normalize_max_workers", "run_ordered_thread_tasks"]
