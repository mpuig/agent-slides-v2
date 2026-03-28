"""Async preview server for deck sidecar live updates."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from agent_slides.io.sidecar import read_deck


class PreviewServer:
    """Watch a deck sidecar file and broadcast deck updates over WebSockets."""

    def __init__(
        self,
        path: str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        poll_interval: float = 0.02,
        debounce_interval: float = 0.05,
    ) -> None:
        self.path = Path(path)
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.debounce_interval = debounce_interval
        self._clients: set[ServerConnection] = set()
        self._server: asyncio.Server | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._debounce_task: asyncio.Task[None] | None = None
        self._closed = False
        self._current_revision: int | None = None
        self._latest_payload: dict[str, Any] | None = None

    @property
    def url(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("Preview server has not started")
        port = self._server.sockets[0].getsockname()[1]
        return f"ws://{self.host}:{port}"

    @property
    def is_running(self) -> bool:
        return self._server is not None and not self._closed and (
            self._watch_task is not None and not self._watch_task.done()
        )

    async def start(self) -> PreviewServer:
        initial_deck = read_deck(str(self.path))
        self._current_revision = initial_deck.revision
        self._server = await serve(self._handle_client, self.host, self.port)
        self._watch_task = asyncio.create_task(self._watch_loop(), name="preview-watch-loop")
        return self

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        if self._debounce_task is not None:
            self._debounce_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._debounce_task

        if self._watch_task is not None:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task

        await asyncio.gather(
            *(client.close() for client in list(self._clients)),
            return_exceptions=True,
        )
        self._clients.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def __aenter__(self) -> PreviewServer:
        return await self.start()

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def _handle_client(self, websocket: ServerConnection) -> None:
        self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    async def _watch_loop(self) -> None:
        while True:
            deck = read_deck(str(self.path))
            if deck.revision != self._current_revision:
                self._current_revision = deck.revision
                self._latest_payload = self._build_message(deck)
                self._schedule_broadcast()
            await asyncio.sleep(self.poll_interval)

    def _schedule_broadcast(self) -> None:
        if self._debounce_task is not None:
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(
            self._debounced_broadcast(),
            name="preview-debounce-broadcast",
        )

    async def _debounced_broadcast(self) -> None:
        try:
            await asyncio.sleep(self.debounce_interval)
            await self._broadcast_latest()
        except asyncio.CancelledError:
            raise

    async def _broadcast_latest(self) -> None:
        if self._latest_payload is None or not self._clients:
            return

        message = json.dumps(self._latest_payload)
        stale_clients: list[ServerConnection] = []
        for client in list(self._clients):
            try:
                await client.send(message)
            except ConnectionClosed:
                stale_clients.append(client)

        for client in stale_clients:
            self._clients.discard(client)

    def _build_message(self, deck: Any) -> dict[str, Any]:
        deck_payload = deck.model_dump(mode="json", by_alias=True)
        return {
            "event": "deck.updated",
            "path": str(self.path),
            "revision": deck.revision,
            "deck": deck_payload,
        }
