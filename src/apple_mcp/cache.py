"""Simple LRU cache for immutable reports."""

from collections import OrderedDict
from typing import Any


class ReportCache:
    def __init__(self, max_entries: int = 100):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            if len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)
            self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()
