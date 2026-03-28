"""HTTP and WebSocket preview server."""

from __future__ import annotations

import asyncio
import json
import threading
from http import HTTPStatus
from pathlib import Path

from websockets.asyncio.server import ServerConnection, broadcast, serve

from agent_slides.io import computed_sidecar_path, read_deck
from agent_slides.preview_runtime.watcher import DeckWatcher

CLIENT_HTML = (Path(__file__).with_name("client.html")).read_text(encoding="utf-8")


class PreviewServer:
    """Serve live preview assets and deck updates on a single port."""

    def __init__(self, deck_path: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._deck_path = Path(deck_path).resolve()
        self._computed_path = computed_sidecar_path(self._deck_path).resolve()
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: Exception | None = None
        self._stop_future: asyncio.Future[None] | None = None
        self._server = None
        self._watcher: DeckWatcher | None = None
        self._payload_json = ""
        self._connections: set[ServerConnection] = set()

    @property
    def url(self) -> str:
        return f"http://localhost:{self._port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="agent-slides-preview", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Preview server did not start within 5 seconds.")
        if self._startup_error is not None:
            raise self._startup_error

    def stop(self) -> None:
        if self._loop is None or self._stop_future is None:
            return

        def _stop() -> None:
            if self._stop_future is not None and not self._stop_future.done():
                self._stop_future.set_result(None)

        self._loop.call_soon_threadsafe(_stop)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:  # pragma: no cover - startup failures are surfaced via start()
            self._startup_error = exc
            self._ready.set()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True),
                )
            self._loop.close()

    async def _serve(self) -> None:
        self._reload_payload(force=True)
        self._stop_future = asyncio.get_running_loop().create_future()
        self._server = await serve(
            self._handle_websocket,
            self._host,
            self._port,
            process_request=self._process_request,
        )
        self._watcher = DeckWatcher(
            [self._deck_path, self._computed_path],
            self._notify_file_change,
        )
        self._watcher.start()
        self._ready.set()

        try:
            await self._stop_future
        finally:
            if self._watcher is not None:
                self._watcher.stop()
            self._server.close()
            await self._server.wait_closed()

    async def _handle_websocket(self, websocket: ServerConnection) -> None:
        self._connections.add(websocket)
        await websocket.send(self._payload_json)
        try:
            await websocket.wait_closed()
        finally:
            self._connections.discard(websocket)

    def _process_request(self, connection: ServerConnection, request):
        path = request.path.split("?", 1)[0]
        if path == "/ws":
            return None
        if path == "/":
            response = connection.respond(HTTPStatus.OK, CLIENT_HTML)
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            return response
        if path == "/api/deck":
            response = connection.respond(HTTPStatus.OK, self._payload_json)
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response

        response = connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        return response

    def _notify_file_change(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._broadcast_latest()))

    async def _broadcast_latest(self) -> None:
        if not self._reload_payload(force=False):
            return
        if self._connections:
            broadcast(self._connections, self._payload_json)

    def _reload_payload(self, *, force: bool) -> bool:
        deck = read_deck(str(self._deck_path))
        payload_json = json.dumps(deck.model_dump(mode="json", by_alias=True))
        if not force and payload_json == self._payload_json:
            return False

        self._payload_json = payload_json
        return True
