"""Filesystem watcher utilities for live preview."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver


class _DeckFileEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        deck_path: Path,
        on_change: Callable[[], None],
        *,
        debounce_seconds: float,
    ) -> None:
        self._deck_path = deck_path.resolve()
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._last_emitted_at = 0.0
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._matches(event):
            return

        now = time.monotonic()
        with self._lock:
            if now - self._last_emitted_at < self._debounce_seconds:
                return
            self._last_emitted_at = now

        self._on_change()

    def _matches(self, event: FileSystemEvent) -> bool:
        candidate_paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]
        for candidate in candidate_paths:
            if candidate is None:
                continue
            if Path(candidate).resolve() == self._deck_path:
                return True
        return False


class DeckWatcher:
    """Watch a single deck file and invoke a callback when it changes."""

    def __init__(
        self,
        deck_path: str | Path,
        on_change: Callable[[], None],
        *,
        debounce_seconds: float = 0.05,
    ) -> None:
        self._deck_path = Path(deck_path).resolve()
        self._observer = PollingObserver(timeout=debounce_seconds)
        self._handler = _DeckFileEventHandler(
            self._deck_path,
            on_change,
            debounce_seconds=debounce_seconds,
        )

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._deck_path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
