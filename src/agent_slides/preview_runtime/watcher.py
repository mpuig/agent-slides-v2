"""Filesystem watcher utilities for live preview."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver


class _DeckFileEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        watched_paths: Iterable[Path],
        on_change: Callable[[], None],
        *,
        debounce_seconds: float,
    ) -> None:
        self._watched_paths = {path.resolve() for path in watched_paths}
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
            if Path(candidate).resolve() in self._watched_paths:
                return True
        return False


class DeckWatcher:
    """Watch a single deck file and invoke a callback when it changes."""

    def __init__(
        self,
        watched_paths: Iterable[str | Path],
        on_change: Callable[[], None],
        *,
        debounce_seconds: float = 0.05,
    ) -> None:
        self._watched_paths = [Path(path).resolve() for path in watched_paths]
        self._observer = PollingObserver(timeout=debounce_seconds)
        self._handler = _DeckFileEventHandler(
            self._watched_paths,
            on_change,
            debounce_seconds=debounce_seconds,
        )

    def start(self) -> None:
        watched_directories = {path.parent for path in self._watched_paths}
        for directory in watched_directories:
            self._observer.schedule(self._handler, str(directory), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
