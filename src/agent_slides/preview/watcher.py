"""Filesystem watcher for preview sidecar updates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from agent_slides.model import load_design_rules
from agent_slides.engine.conditional_formatting import preview_conditional_formatting_payload
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND
from agent_slides.icons import require_icon
from agent_slides.io import read_deck

DeckPayload = dict[str, Any]
UpdateCallback = Callable[[DeckPayload], Awaitable[None]]


def _enrich_icon_payload(payload: dict[str, Any]) -> dict[str, Any]:
    hydrated = deepcopy(payload)
    for slide in hydrated.get("slides", []):
        for node in slide.get("nodes", []):
            if node.get("type") == "icon" and isinstance(node.get("icon_name"), str):
                node["icon_svg_path"] = require_icon(str(node["icon_name"]))

            blocks = node.get("content", {}).get("blocks", [])
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                icon_name = block.get("icon")
                if isinstance(icon_name, str) and icon_name.strip():
                    block["icon_svg_path"] = require_icon(icon_name)
    return hydrated


def load_deck_payload(sidecar_path: Path) -> tuple[int, DeckPayload]:
    """Read the current deck payload and revision from disk."""

    deck = read_deck(str(sidecar_path))
    payload = deck.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["conditional_formatting"] = preview_conditional_formatting_payload(load_design_rules(deck.design_rules))
    return deck.revision, _enrich_icon_payload(payload)


def _payload_digest(payload: DeckPayload) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(serialized).hexdigest()


class _SidecarEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: SidecarWatcher) -> None:
        self._watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        if self._watcher.matches_event(event):
            self._watcher.notify_filesystem_event()


class SidecarWatcher:
    """Watch a sidecar file path and publish updates when the deck payload changes."""

    def __init__(
        self,
        sidecar_path: str | Path,
        on_revision_change: UpdateCallback,
        *,
        watched_path: str | Path | None = None,
        debounce_ms: int = 50,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sidecar_path = Path(sidecar_path).resolve()
        self.watched_path = (
            Path(watched_path).resolve() if watched_path is not None else self.sidecar_path
        )
        self._on_revision_change = on_revision_change
        self._debounce_seconds = max(debounce_ms, 0) / 1000
        self._logger = logger or logging.getLogger(__name__)
        self._observer: Observer | PollingObserver | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_check: asyncio.TimerHandle | None = None
        self._last_seen_payload_digest: str | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._last_seen_payload_digest = self._read_last_seen_payload_digest()
        self._observer = self._build_observer()
        self._observer.schedule(
            _SidecarEventHandler(self),
            str(self.watched_path.parent),
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
        target = str(self.watched_path)

        return any(path and str(Path(path).resolve()) == target for path in paths)

    def notify_filesystem_event(self) -> None:
        if self._loop is None:
            return

        self._loop.call_soon_threadsafe(self._schedule_debounced_check)

    async def check_for_update(self) -> bool:
        try:
            _, payload = load_deck_payload(self.sidecar_path)
        except AgentSlidesError as exc:
            if exc.code != FILE_NOT_FOUND:
                self._logger.warning("Preview watcher skipped update: %s", exc.message)
            return False

        payload_digest = _payload_digest(payload)
        if payload_digest == self._last_seen_payload_digest:
            return False

        self._last_seen_payload_digest = payload_digest
        await self._on_revision_change(payload)
        return True

    def _read_last_seen_payload_digest(self) -> str | None:
        try:
            _, payload = load_deck_payload(self.sidecar_path)
        except AgentSlidesError as exc:
            if exc.code != FILE_NOT_FOUND:
                self._logger.warning("Preview watcher could not read initial deck: %s", exc.message)
            return None

        return _payload_digest(payload)

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
