"""Bounded concurrency for independent Jira reads."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_JIRA_WORKERS = 6
_WORKERS_ENV = "ARTIFACT_JIRA_WORKERS"


def jira_workers() -> int:
    """Worker count for concurrent Jira reads (``ARTIFACT_JIRA_WORKERS``; 1 disables concurrency)."""
    raw = os.environ.get(_WORKERS_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_JIRA_WORKERS


def map_concurrently(
    fn: Callable[[T], R],
    items: Iterable[T],
    on_result: Callable[[T, R], None],
    *,
    workers: int | None = None,
) -> None:
    """Run ``fn`` over ``items`` on a thread pool; call ``on_result`` for each as it completes.

    ``on_result`` always runs on the calling thread, so it may safely mutate shared state
    (caches, counters) without locking. The first exception from ``fn`` is re-raised after
    pending work is cancelled; results already delivered to ``on_result`` are kept.
    """
    work = list(items)
    count = jira_workers() if workers is None else max(1, workers)
    if count == 1 or len(work) <= 1:
        for item in work:
            on_result(item, fn(item))
        return

    with ThreadPoolExecutor(max_workers=min(count, len(work))) as pool:
        futures = {pool.submit(fn, item): item for item in work}
        try:
            for future in as_completed(futures):
                on_result(futures[future], future.result())
        except BaseException:
            # Queued work is dropped; calls already in flight finish when the pool exits.
            for future in futures:
                future.cancel()
            raise
