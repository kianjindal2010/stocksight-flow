from collections import OrderedDict
from concurrent.futures import Future
from threading import Lock
from time import monotonic
from typing import Any, Callable


class PageCache:
    """Reuse a completed panel response and share an in-flight refresh."""

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        self._pending: dict[tuple, Future] = {}
        self._lock = Lock()

    def peek(self, key: tuple) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            return entry[1] if entry and entry[0] > monotonic() else None

    def load(self, key: tuple, seconds: float, fetch: Callable[[], Any]) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry[0] > monotonic():
                self._entries.move_to_end(key)
                return entry[1]
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = self._pending[key] = Future()
        if not owner:
            return pending.result()
        try:
            value = fetch()
            with self._lock:
                self._entries[key] = (monotonic() + seconds, value)
                self._entries.move_to_end(key)
                while len(self._entries) > 128:
                    self._entries.popitem(last=False)
            pending.set_result(value)
            return value
        except Exception as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)
