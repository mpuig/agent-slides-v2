"""HTTP and WebSocket preview server for live deck updates."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import mimetypes
import signal
from http import HTTPStatus
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from websockets.datastructures import Headers
from websockets.http11 import Response
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND
from agent_slides.io.assets import resolve_image_path
from agent_slides.preview.renderer import SlideRenderError, SlideRenderer
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
        slide_renderer: SlideRenderer | None = None,
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
        self._preview_clients: set[ServerConnection] = set()
        self._preview_backend = "svg"
        self._preview_payload: dict[str, Any] | None = None
        self._slide_previews: list[dict[str, Any]] = []
        self._renderer = slide_renderer
        if self._renderer is None:
            self._renderer = SlideRenderer(self.sidecar_path)
        self._logged_png_fallback_warning = False

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
        await self._prime_preview_state()
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
        if not self._preview_clients:
            return

        broadcast(self._preview_clients, json.dumps(payload))

    @property
    def _png_preview_enabled(self) -> bool:
        return bool(self._renderer is not None and self._renderer.is_available and self._preview_backend == "png")

    async def _prime_preview_state(self) -> None:
        try:
            _, payload = load_deck_payload(self.sidecar_path)
        except AgentSlidesError:
            self._preview_backend = "svg"
            self._preview_payload = None
            self._slide_previews = []
            return

        self._preview_payload = payload
        if self._renderer is None:
            self._preview_backend = "svg"
            self._slide_previews = []
            return

        if not self._renderer.is_available:
            self._preview_backend = "svg"
            self._slide_previews = []
            self._log_png_fallback_warning()
            return

        try:
            await self._renderer.render_all()
        except SlideRenderError as exc:
            self._logger.warning("PNG preview render failed; falling back to SVG preview: %s", exc)
            self._preview_backend = "svg"
            self._slide_previews = []
            return

        self._preview_backend = "png"
        self._slide_previews = self._build_slide_previews(payload)

    def _log_png_fallback_warning(self) -> None:
        if self._logged_png_fallback_warning:
            return
        self._logged_png_fallback_warning = True
        self._logger.warning(
            "LibreOffice not found. Using approximate SVG preview. Install LibreOffice for pixel-perfect rendering."
        )

    async def _render_changed_slides(
        self,
        payload: dict[str, Any],
        changed_indices: list[int],
    ) -> None:
        if self._renderer is None or not changed_indices:
            return

        await self._renderer.render_indices(changed_indices)
        self._preview_backend = "png"

    def _slide_revision(self, slide_payload: dict[str, Any], deck_revision: int) -> int:
        return int(slide_payload.get("revision", deck_revision))

    def _slide_signature(self, payload: dict[str, Any]) -> list[tuple[str, int]]:
        deck_revision = int(payload["revision"])
        return [
            (str(slide["slide_id"]), self._slide_revision(slide, deck_revision))
            for slide in payload.get("slides", [])
        ]

    def _changed_slide_indices(
        self,
        previous_payload: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> list[int]:
        slides = payload.get("slides", [])
        if previous_payload is None:
            return list(range(len(slides)))

        previous_signature = self._slide_signature(previous_payload)
        current_signature = self._slide_signature(payload)
        if len(previous_signature) != len(current_signature):
            return list(range(len(slides)))
        if any(previous_id != current_id for (previous_id, _), (current_id, _) in zip(previous_signature, current_signature)):
            return list(range(len(slides)))
        return [
            index
            for index, ((_, previous_revision), (_, current_revision)) in enumerate(
                zip(previous_signature, current_signature)
            )
            if previous_revision != current_revision
        ]

    def _build_slide_previews(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        deck_revision = int(payload["revision"])
        return [
            {
                "index": index,
                "url": f"/slides/{index}.png?rev={self._slide_revision(slide, deck_revision)}",
                "revision": self._slide_revision(slide, deck_revision),
            }
            for index, slide in enumerate(payload.get("slides", []))
        ]

    async def _broadcast_update(self, payload: dict[str, Any]) -> None:
        previous_payload = self._preview_payload
        self._preview_payload = payload

        if not self._png_preview_enabled:
            await self.broadcast_payload(self._build_update_message(payload))
            return

        changed_indices = self._changed_slide_indices(previous_payload, payload)
        try:
            if changed_indices:
                await self._render_changed_slides(payload, changed_indices)
            self._slide_previews = self._build_slide_previews(payload)
        except SlideRenderError as exc:
            self._logger.warning("PNG preview render failed; falling back to SVG preview: %s", exc)
            self._preview_backend = "svg"
            await self.broadcast_payload(self._build_update_message(payload))
            return

        await self.broadcast_payload(self._build_update_message(payload, changed_indices=changed_indices))

    async def _handle_websocket(self, websocket: ServerConnection) -> None:
        if websocket.request.path == "/ws":
            await self._handle_preview_websocket(websocket)

    async def _handle_preview_websocket(self, websocket: ServerConnection) -> None:
        self._preview_clients.add(websocket)
        self._logger.info("Preview client connected: %s", websocket.remote_address)

        try:
            await websocket.wait_closed()
        finally:
            self._preview_clients.discard(websocket)
            self._logger.info("Preview client disconnected: %s", websocket.remote_address)

    def _process_request(self, connection: ServerConnection, request: Any) -> Any:
        request_path = request.path.partition("?")[0]

        if request_path == "/ws":
            return None

        if request_path == "/chat/ws":
            return self._not_found_response(connection)

        if request_path == "/client.html":
            response = connection.respond(HTTPStatus.OK, CLIENT_HTML)
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            return response

        if request_path == "/":
            response = connection.respond(HTTPStatus.OK, CLIENT_HTML)
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            return response

        if request_path in {"/chat", "/chat.html"}:
            return self._not_found_response(connection)

        if request_path == "/api/deck":
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

        if request_path.startswith("/slides/") and request_path.endswith(".png"):
            index_text = request_path.removeprefix("/slides/").removesuffix(".png")

            try:
                payload, content_type = self._read_slide_png_bytes(index_text)
            except AgentSlidesError as exc:
                status = HTTPStatus.NOT_FOUND if exc.code == FILE_NOT_FOUND else HTTPStatus.INTERNAL_SERVER_ERROR
                response = connection.respond(status, f"{exc.message}\n")
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
                return response

            return Response(
                HTTPStatus.OK.value,
                HTTPStatus.OK.phrase,
                Headers(
                    {
                        "Content-Type": content_type,
                        "Content-Length": str(len(payload)),
                    }
                ),
                payload,
            )

        if request_path.startswith("/api/images/"):
            relative_path = unquote(request_path.removeprefix("/api/images/"))

            try:
                payload, content_type = self._read_image_bytes(relative_path)
            except AgentSlidesError as exc:
                status = HTTPStatus.NOT_FOUND if exc.code == FILE_NOT_FOUND else HTTPStatus.INTERNAL_SERVER_ERROR
                response = connection.respond(status, f"{exc.message}\n")
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
                return response

            return Response(
                HTTPStatus.OK.value,
                HTTPStatus.OK.phrase,
                Headers(
                    {
                        "Content-Type": content_type,
                        "Content-Length": str(len(payload)),
                    }
                ),
                payload,
            )

        if request_path.startswith("/download/"):
            filename = unquote(request_path.removeprefix("/download/"))

            try:
                payload, content_type, download_name = self._read_download_bytes(filename)
            except AgentSlidesError as exc:
                status = HTTPStatus.NOT_FOUND if exc.code == FILE_NOT_FOUND else HTTPStatus.INTERNAL_SERVER_ERROR
                response = connection.respond(status, f"{exc.message}\n")
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
                return response

            return Response(
                HTTPStatus.OK.value,
                HTTPStatus.OK.phrase,
                Headers(
                    {
                        "Content-Disposition": f'attachment; filename="{download_name}"',
                        "Content-Type": content_type,
                        "Content-Length": str(len(payload)),
                    }
                ),
                payload,
            )

        return self._not_found_response(connection)

    def _read_deck_json(self) -> str:
        if self._preview_payload is None:
            _, self._preview_payload = load_deck_payload(self.sidecar_path)
        payload = dict(self._preview_payload)
        payload["preview_backend"] = self._preview_backend
        if self._preview_backend == "png":
            payload["slide_previews"] = list(self._slide_previews)
        return json.dumps(payload)

    def _read_image_bytes(self, image_path: str) -> tuple[bytes, str]:
        resolved = resolve_image_path(image_path, base_dir=self.sidecar_path.parent)
        content_type, _ = mimetypes.guess_type(resolved.name)
        return resolved.read_bytes(), content_type or "application/octet-stream"

    def _read_slide_png_bytes(self, slide_index_text: str) -> tuple[bytes, str]:
        if self._preview_backend != "png" or self._renderer is None or self._preview_payload is None:
            raise AgentSlidesError(FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}")

        try:
            slide_index = int(slide_index_text)
        except ValueError as exc:
            raise AgentSlidesError(FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}") from exc

        slides = self._preview_payload.get("slides", [])
        if slide_index < 0 or slide_index >= len(slides):
            raise AgentSlidesError(FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}")

        slide = slides[slide_index]
        slide_id = str(slide["slide_id"])
        slide_revision = self._slide_revision(slide, int(self._preview_payload["revision"]))
        rendered = self._renderer.get_cached(slide_id, slide_revision)
        if rendered is None:
            raise AgentSlidesError(FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}")

        return rendered.read_bytes(), "image/png"

    def _read_download_bytes(self, filename: str) -> tuple[bytes, str, str]:
        requested = Path(filename)
        resolved = (self.sidecar_path.parent / requested).resolve()
        if (
            not filename
            or requested.name != filename
            or requested.is_absolute()
            or resolved.parent != self.sidecar_path.parent
            or resolved.suffix.lower() != ".pptx"
            or not resolved.is_file()
        ):
            raise AgentSlidesError(FILE_NOT_FOUND, f"Download file not found: {filename}")

        content_type, _ = mimetypes.guess_type(resolved.name)
        return (
            resolved.read_bytes(),
            content_type or "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resolved.name,
        )

    def _build_update_message(
        self,
        payload: dict[str, Any],
        *,
        changed_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        if self._preview_backend == "png":
            previews = self._build_slide_previews(payload)
            return {
                "type": "slides_updated",
                "path": str(self.sidecar_path),
                "revision": payload["revision"],
                "slide_count": len(payload.get("slides", [])),
                "slides": [
                    previews[index]
                    for index in (changed_indices or list(range(len(previews))))
                ],
            }

        return {
            "event": "deck.updated",
            "path": str(self.sidecar_path),
            "revision": payload["revision"],
            "deck": payload,
        }

    def _not_found_response(self, connection: ServerConnection) -> Any:
        response = connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        return response


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
