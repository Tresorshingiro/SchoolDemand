"""One background thread for checks, publishing and withdrawals: one job at a time, in the order asked."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

log = logging.getLogger("school_planning.imports")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="imports")
_futures: list[Future] = []
_lock = threading.Lock()


def _logged(fn, *args):
    try:
        fn(*args)
    except Exception:  # noqa: BLE001 — the jobs record their own failures; this is the last resort
        log.exception("import job %s%s failed", fn.__name__, args)


def submit(fn, *args) -> Future:
    with _lock:
        f = _executor.submit(_logged, fn, *args)
        _futures[:] = [x for x in _futures if not x.done()] + [f]
    return f


def wait_idle(timeout: float = 900) -> None:
    """Wait until every job asked so far has finished (tests, the command line)."""
    with _lock:
        pending = list(_futures)
    for f in pending:
        f.result(timeout=timeout)
