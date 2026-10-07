"""Lightweight in-process background work — no broker, no extra service.

Two primitives, following the pattern services/location_sweep.py already
uses:

* ``submit(fn, *args)`` runs a one-off job (research a company, transcribe a
  recording, run a sync) on a small thread pool so the HTTP request that
  asked for it returns immediately.
* ``start_periodic_tasks()`` runs scheduled jobs (Bigin reconciliation,
  transcription polling) in daemon threads.

Job state always lives in Postgres (a status column on the row being worked
on), never only in memory: if the process restarts mid-job, a periodic task
finds the unfinished rows and resumes them. Scheduled jobs take a Postgres
advisory lock, so several API replicas never run the same job twice at once.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import func, select

from app.core.config import get_settings

logger = logging.getLogger("app.background")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-job")


def submit(fn: Callable, *args, **kwargs) -> None:
    """Run ``fn`` in the background. Exceptions are logged, never raised to
    the caller — jobs record their own failure state in the database."""

    def run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Background job %s failed", getattr(fn, "__name__", fn))

    if get_settings().environment == "test":
        # Tests drive jobs explicitly; nothing runs behind their back.
        return
    _executor.submit(run)


@contextmanager
def advisory_lock(key: int):
    """Yield True if this process got the (non-blocking) advisory lock."""
    from app.db.session import engine

    with engine.connect() as conn:
        acquired = bool(conn.execute(select(func.pg_try_advisory_lock(key))).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(select(func.pg_advisory_unlock(key)))
                conn.commit()


@dataclass
class PeriodicTask:
    name: str
    interval_seconds: float
    fn: Callable[[], object]
    startup_delay_seconds: float = 30
    lock_key: int | None = None


def _loop(task: PeriodicTask, stop: threading.Event) -> None:
    if stop.wait(task.startup_delay_seconds):
        return
    while True:
        try:
            if task.lock_key is None:
                task.fn()
            else:
                with advisory_lock(task.lock_key) as acquired:
                    if acquired:
                        task.fn()
        except Exception:
            logger.exception("Periodic task %s failed", task.name)
        if stop.wait(task.interval_seconds):
            return


def start_periodic_tasks(tasks: list[PeriodicTask]) -> threading.Event | None:
    """Start each task in a daemon thread. Returns an Event that stops them
    all when set, or None in tests."""
    if get_settings().environment == "test":
        return None
    stop = threading.Event()
    for task in tasks:
        if task.interval_seconds <= 0:
            continue
        threading.Thread(target=_loop, args=(task, stop), name=f"periodic-{task.name}", daemon=True).start()
    return stop
