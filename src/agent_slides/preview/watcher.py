"""Filesystem watcher for preview sidecar updates."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND
from agent_slides.io import read_deck

DeckPayload = dict[str, Any]
UpdateCallback = Callable[[DeckPayload], Awaitable[None]]


def load_deck_payload(sidecar_path: Path) -> tuple[int, DeckPayload]:
    """Read the current deck payload and revision from disk."""

    deck = read_deck(str(sidecar_path))
    return deck.revision, deck.model_dump(mode="json", by_alias=True)


class _SidecarEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: SidecarWatcher) -> None:
        self._watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        if self._watcher.matches_event(event):
            self._watcher.notify_filesystem_event()


class SidecarWatcher:
    """Watch a deck sidecar file and publish updates on revision changes."""

    def __init__(
        self,
        sidecar_path: str | Path,
        on_revision_change: UpdateCallback,
        *,
        debounce_ms: int = 50,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sidecar_path = Path(sidecar_path).resolve()
        self._on_revision_change = on_revision_change
        self._debounce_seconds = debounce_ms / 1000
        self._logger = logger or logging.getLogger(__name__)
        self._observer: Observer | PollingObserver | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_check: asyncio.TimerHandle | None = None
        self._last_seen_revision: int | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._last_seen_revision = self._read_last_seen_revision()
        self._observer = self._build_observer()
        self._observer.schedule(
            _SidecarEventHandler(self),
            str(self.sidecar_path.parent),
            recursive=False,
        )
        self._observer.start()

    async def stop(self) -> None:
        if self._pending_check is not None:
            self._pending_check.cancel()
            self._pending_check = None

        if self._observer is None:
            return

        self._observer.stop()
        await asyncio.to_thread(self._observer.join, 1.0)
        self._observer = None

    def matches_event(self, event: FileSystemEvent) -> bool:
        paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]
        target = str(self.sidecar_path)

        return any(path and str(Path(path).resolve()) == target for path in paths)

    def notify_filesystem_event(self) -> None:
        if self._loop is None:
            return

        self._loop.call_soon_threadsafe(self._schedule_debounced_check)

    async def check_for_update(self) -> bool:
        try:
            revision, payload = load_deck_payload(self.sidecar_path)
        except AgentSlidesError as exc:
            if exc.code != FILE_NOT_FOUND:
                self._logger.warning("Preview watcher skipped update: %s", exc.message)
            return False

        if revision == self._last_seen_revision:
            return False

        self._last_seen_revision = revision
        await self._on_revision_change(payload)
        return True

    def _read_last_seen_revision(self) -> int | None:
        try:
            revision, _ = load_deck_payload(self.sidecar_path)
        except AgentSlidesError as exc:
            if exc.code != FILE_NOT_FOUND:
                self._logger.warning("Preview watcher could not read initial deck: %s", exc.message)
            return None

        return revision

    def _schedule_debounced_check(self) -> None:
        if self._pending_check is not None:
            self._pending_check.cancel()

        loop = self._loop
        if loop is None:
            return

        self._pending_check = loop.call_later(
            self._debounce_seconds,
            lambda: asyncio.create_task(self._run_check()),
        )

    async def _run_check(self) -> None:
        self._pending_check = None
        await self.check_for_update()

    def _build_observer(self) -> Observer | PollingObserver:
        if sys.platform == "darwin":
            return PollingObserver(timeout=max(self._debounce_seconds, 0.05))

        return Observer()
