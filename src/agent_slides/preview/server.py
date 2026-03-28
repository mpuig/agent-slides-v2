"""HTTP and WebSocket preview server for live deck updates."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from http import HTTPStatus
from importlib import resources
from pathlib import Path
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND
from agent_slides.preview.watcher import SidecarWatcher, load_deck_payload

LOGGER = logging.getLogger(__name__)
CLIENT_HTML = resources.files("agent_slides.preview").joinpath("client.html").read_text(
    encoding="utf-8"
)


class PreviewServer:
    """Serve the preview client, deck payload, and live deck updates."""

    def __init__(
        self,
        sidecar_path: str | Path,
        *,
        host: str = "localhost",
        port: int = 8765,
        debounce_ms: int | None = None,
        debounce_interval: float | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sidecar_path = Path(sidecar_path).resolve()
        self.host = host
        self.port = port
        effective_debounce_ms = debounce_ms
        if debounce_interval is not None:
            effective_debounce_ms = int(debounce_interval * 1000)
        if effective_debounce_ms is None:
            effective_debounce_ms = 50
        self._logger = logger or LOGGER
        self._watcher = SidecarWatcher(
            self.sidecar_path,
            self._broadcast_update,
            debounce_ms=effective_debounce_ms,
            logger=self._logger,
        )
        self._server: Server | None = None
        self._clients: set[ServerConnection] = set()

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"

    @property
    def is_running(self) -> bool:
        return self._server is not None

    async def __aenter__(self) -> PreviewServer:
        return await self.start()

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    async def start(self) -> PreviewServer:
        if self._server is not None:
            return self

        self._server = await serve(
            self._handle_websocket,
            self.host,
            self.port,
            process_request=self._process_request,
        )

        socket = next(iter(self._server.sockets or []), None)
        if socket is not None:
            self.port = int(socket.getsockname()[1])

        await self._watcher.start()
        return self

    async def stop(self) -> None:
        await self._watcher.stop()

        if self._server is None:
            return

        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def close(self) -> None:
        await self.stop()

    async def serve_forever(self, stop_event: asyncio.Event | None = None) -> None:
        local_stop = stop_event or asyncio.Event()
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, local_stop.set)
            except NotImplementedError:
                pass

        async with self:
            await local_stop.wait()

    async def broadcast_payload(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return

        broadcast(self._clients, json.dumps(payload))

    async def _broadcast_update(self, payload: dict[str, Any]) -> None:
        await self.broadcast_payload(self._build_update_message(payload))

    async def _handle_websocket(self, websocket: ServerConnection) -> None:
        if websocket.request.path != "/ws":
            return

        self._clients.add(websocket)
        self._logger.info("Preview client connected: %s", websocket.remote_address)

        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)
            self._logger.info("Preview client disconnected: %s", websocket.remote_address)

    def _process_request(self, connection: ServerConnection, request: Any) -> Any:
        if request.path == "/ws":
            return None

        if request.path == "/":
            response = connection.respond(HTTPStatus.OK, CLIENT_HTML)
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            return response

        if request.path == "/api/deck":
            try:
                payload = self._read_deck_json()
            except AgentSlidesError as exc:
                status = HTTPStatus.NOT_FOUND if exc.code == FILE_NOT_FOUND else HTTPStatus.INTERNAL_SERVER_ERROR
                response = connection.respond(status, f"{exc.message}\n")
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
                return response

            response = connection.respond(HTTPStatus.OK, payload)
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response

        response = connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        return response

    def _read_deck_json(self) -> str:
        _, payload = load_deck_payload(self.sidecar_path)
        return json.dumps(payload)

    def _build_update_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": "deck.updated",
            "path": str(self.sidecar_path),
            "revision": payload["revision"],
            "deck": payload,
        }


async def run_preview_server(
    sidecar_path: str | Path,
    *,
    host: str = "localhost",
    port: int = 8765,
    debounce_ms: int = 50,
) -> None:
    """Run the preview server until interrupted."""

    server = PreviewServer(
        sidecar_path,
        host=host,
        port=port,
        debounce_ms=debounce_ms,
    )
    await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agent-slides live preview server.")
    parser.add_argument("path", help="Path to the sidecar deck JSON file.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debounce-ms", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(
        run_preview_server(
            args.path,
            host=args.host,
            port=args.port,
            debounce_ms=args.debounce_ms,
        )
    )


if __name__ == "__main__":
    main()
