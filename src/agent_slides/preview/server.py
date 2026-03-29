"""HTTP and WebSocket preview server for live deck updates."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import mimetypes
import signal
import threading
from http import HTTPStatus
from importlib import resources
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from websockets.datastructures import Headers
from websockets.http11 import Response
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND
from agent_slides.io import computed_sidecar_path
from agent_slides.io.assets import resolve_image_path
from agent_slides.preview.renderer import SlideRenderError, SlideRenderer
from agent_slides.preview.watcher import SidecarWatcher, load_deck_payload

LOGGER = logging.getLogger(__name__)
CLIENT_HTML = (
    resources.files("agent_slides.preview")
    .joinpath("client.html")
    .read_text(encoding="utf-8")
)
APPROXIMATE_PREVIEW_NOTICE = "Approximate preview (LibreOffice unavailable)"


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
        on_listening: Callable[[], None] | None = None,
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
            watched_path=computed_sidecar_path(self.sidecar_path),
            debounce_ms=effective_debounce_ms,
            logger=self._logger,
        )
        self._server: Server | None = None
        self._preview_clients: set[ServerConnection] = set()
        self._preview_backend = "svg"
        self._preview_payload: dict[str, Any] | None = None
        self._slide_previews: list[dict[str, Any]] = []
        self._rendering_payload: dict[str, Any] | None = None
        self._renderer = slide_renderer
        if self._renderer is None:
            self._renderer = SlideRenderer(self.sidecar_path)
        self._logged_png_fallback_warning = False
        self._logged_png_cache_fallback_warning = False
        self._on_listening = on_listening

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
        if self._on_listening is not None:
            self._on_listening()

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

    def _set_svg_preview(self) -> None:
        self._preview_backend = "svg"
        self._slide_previews = []
        self._rendering_payload = None

    def _missing_slide_previews(
        self,
        payload: dict[str, Any],
        slide_indices: list[int] | None = None,
    ) -> list[int]:
        if self._renderer is None:
            if slide_indices is not None:
                return list(slide_indices)
            return list(range(len(payload.get("slides", []))))

        slides = payload.get("slides", [])
        deck_revision = int(payload["revision"])
        indices = (
            slide_indices if slide_indices is not None else list(range(len(slides)))
        )
        missing: list[int] = []
        for index in indices:
            if index < 0 or index >= len(slides):
                continue
            slide = slides[index]
            slide_id = str(slide["slide_id"])
            slide_revision = self._slide_revision(slide, deck_revision)
            if self._renderer.get_cached(slide_id, slide_revision) is None:
                missing.append(index)
        return missing

    def _log_missing_png_cache_warning(self, missing_indices: list[int]) -> None:
        if self._logged_png_cache_fallback_warning:
            return
        self._logged_png_cache_fallback_warning = True
        self._logger.warning(
            "PNG preview render did not produce cached slide images for indices %s; falling back to SVG preview.",
            missing_indices,
        )

    def _preview_deck_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        preview_payload = dict(payload)
        preview_payload["preview_backend"] = self._preview_backend
        if self._preview_backend == "png":
            preview_payload["slide_previews"] = list(self._slide_previews)
        elif payload.get("slides"):
            preview_payload["preview_notice"] = APPROXIMATE_PREVIEW_NOTICE
        return preview_payload

    async def _prime_preview_state(self) -> None:
        try:
            _, payload = load_deck_payload(self.sidecar_path)
        except AgentSlidesError:
            self._set_svg_preview()
            self._preview_payload = None
            return

        self._preview_payload = payload
        if self._renderer is None:
            self._set_svg_preview()
            return

        if not self._renderer.is_available:
            self._set_svg_preview()
            self._log_png_fallback_warning()
            return

        try:
            await self._render_all_slides(payload)
        except SlideRenderError as exc:
            self._logger.warning(
                "PNG preview render failed; falling back to SVG preview: %s", exc
            )
            self._set_svg_preview()
            return

        missing_indices = self._missing_slide_previews(payload)
        if missing_indices:
            self._log_missing_png_cache_warning(missing_indices)
            self._set_svg_preview()
            return

        self._preview_backend = "png"
        self._slide_previews = self._build_slide_previews(payload)
        self._rendering_payload = None

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

        await self._render_indices(payload, changed_indices)
        missing_indices = self._missing_slide_previews(payload, changed_indices)
        if missing_indices:
            raise SlideRenderError(
                f"Renderer did not produce cached PNG previews for slide indices {missing_indices}."
            )
        self._preview_backend = "png"

    def _build_rendering_message(self, slide_index: int, total: int) -> dict[str, Any]:
        return {
            "type": "rendering",
            "path": str(self.sidecar_path),
            "slide_index": slide_index + 1,
            "total": total,
        }

    async def _set_rendering_progress(self, slide_index: int, total: int) -> None:
        self._rendering_payload = self._build_rendering_message(slide_index, total)
        await self.broadcast_payload(self._rendering_payload)

    async def _render_all_slides(self, payload: dict[str, Any]) -> None:
        if self._renderer is None:
            return
        total = len(payload.get("slides", []))
        if total == 0:
            self._rendering_payload = None
            return

        await self._set_rendering_progress(0, total)
        loop = asyncio.get_running_loop()
        first_progress = True
        progress_lock = threading.Lock()

        def progress_callback(slide_index: int, total_slides: int) -> None:
            nonlocal first_progress
            with progress_lock:
                if first_progress:
                    first_progress = False
                    return
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    self._set_rendering_progress(slide_index, total_slides)
                )
            )

        await self._renderer.render_all(progress_callback=progress_callback)
        self._rendering_payload = None

    async def _render_indices(
        self, payload: dict[str, Any], slide_indices: list[int]
    ) -> None:
        if self._renderer is None or not slide_indices:
            return

        total = len(payload.get("slides", []))
        first_slide_index = slide_indices[0]
        await self._set_rendering_progress(first_slide_index, total)

        loop = asyncio.get_running_loop()
        first_progress = True
        progress_lock = threading.Lock()

        def progress_callback(slide_index: int, total_slides: int) -> None:
            nonlocal first_progress
            with progress_lock:
                if first_progress:
                    first_progress = False
                    return
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    self._set_rendering_progress(slide_index, total_slides)
                )
            )

        await self._renderer.render_indices(
            slide_indices, progress_callback=progress_callback
        )
        self._rendering_payload = None

    def _slide_revision(self, slide_payload: dict[str, Any], deck_revision: int) -> int:
        return int(slide_payload.get("revision", deck_revision))

    def _slide_signature(self, payload: dict[str, Any]) -> list[tuple[str, int, str]]:
        deck_revision = int(payload["revision"])
        return [
            (
                str(slide["slide_id"]),
                self._slide_revision(slide, deck_revision),
                json.dumps(slide, sort_keys=True, separators=(",", ":")),
            )
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
        if any(
            previous_id != current_id
            for (previous_id, _, _), (current_id, _, _) in zip(
                previous_signature, current_signature
            )
        ):
            return list(range(len(slides)))
        return [
            index
            for index, (
                (_, previous_revision, previous_slide),
                (_, current_revision, current_slide),
            ) in enumerate(zip(previous_signature, current_signature))
            if previous_revision != current_revision or previous_slide != current_slide
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

        if self._renderer is None:
            await self.broadcast_payload(self._build_update_message(payload))
            return

        if not self._renderer.is_available:
            self._preview_backend = "svg"
            self._slide_previews = []
            self._log_png_fallback_warning()
            await self.broadcast_payload(self._build_update_message(payload))
            return

        changed_indices = self._changed_slide_indices(previous_payload, payload)
        try:
            if changed_indices:
                await self._render_changed_slides(payload, changed_indices)
            self._slide_previews = self._build_slide_previews(payload)
        except SlideRenderError as exc:
            self._logger.warning(
                "PNG preview render failed; falling back to SVG preview: %s", exc
            )
            self._set_svg_preview()
            await self.broadcast_payload(self._build_update_message(payload))
            return

        await self.broadcast_payload(
            self._build_update_message(payload, changed_indices=changed_indices)
        )

    async def _handle_websocket(self, websocket: ServerConnection) -> None:
        if websocket.request.path == "/ws":
            await self._handle_preview_websocket(websocket)

    async def _handle_preview_websocket(self, websocket: ServerConnection) -> None:
        self._preview_clients.add(websocket)
        self._logger.info("Preview client connected: %s", websocket.remote_address)

        try:
            payload = self._preview_payload
            if payload is None:
                await websocket.send(json.dumps(self._build_waiting_update_message()))
            else:
                await websocket.send(json.dumps(self._build_update_message(payload)))
                if self._rendering_payload is not None:
                    await websocket.send(json.dumps(self._rendering_payload))
            await websocket.wait_closed()
        finally:
            self._preview_clients.discard(websocket)
            self._logger.info(
                "Preview client disconnected: %s", websocket.remote_address
            )

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
                status = (
                    HTTPStatus.NOT_FOUND
                    if exc.code == FILE_NOT_FOUND
                    else HTTPStatus.INTERNAL_SERVER_ERROR
                )
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
                status = (
                    HTTPStatus.NOT_FOUND
                    if exc.code == FILE_NOT_FOUND
                    else HTTPStatus.INTERNAL_SERVER_ERROR
                )
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
                status = (
                    HTTPStatus.NOT_FOUND
                    if exc.code == FILE_NOT_FOUND
                    else HTTPStatus.INTERNAL_SERVER_ERROR
                )
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
                payload, content_type, download_name = self._read_download_bytes(
                    filename
                )
            except AgentSlidesError as exc:
                status = (
                    HTTPStatus.NOT_FOUND
                    if exc.code == FILE_NOT_FOUND
                    else HTTPStatus.INTERNAL_SERVER_ERROR
                )
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
        payload = self._client_payload()
        return json.dumps(payload)

    def _client_payload(self) -> dict[str, Any]:
        if self._preview_payload is None:
            try:
                _, self._preview_payload = load_deck_payload(self.sidecar_path)
            except AgentSlidesError as exc:
                if exc.code == FILE_NOT_FOUND:
                    return self._build_waiting_payload()
                raise
        return self._preview_deck_payload(self._preview_payload)

    def _build_waiting_payload(self) -> dict[str, Any]:
        return {
            "status": "waiting",
            "message": "Waiting for deck...",
            "path": str(self.sidecar_path),
            "revision": 0,
            "slides": [],
            "preview_backend": "svg",
        }

    def _build_waiting_update_message(self) -> dict[str, Any]:
        payload = self._build_waiting_payload()
        return {
            "event": "deck.updated",
            "path": str(self.sidecar_path),
            "revision": 0,
            "deck": payload,
        }

    def _read_image_bytes(self, image_path: str) -> tuple[bytes, str]:
        resolved = resolve_image_path(image_path, base_dir=self.sidecar_path.parent)
        content_type, _ = mimetypes.guess_type(resolved.name)
        return resolved.read_bytes(), content_type or "application/octet-stream"

    def _read_slide_png_bytes(self, slide_index_text: str) -> tuple[bytes, str]:
        if (
            self._preview_backend != "png"
            or self._renderer is None
            or self._preview_payload is None
        ):
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}"
            )

        try:
            slide_index = int(slide_index_text)
        except ValueError as exc:
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}"
            ) from exc

        slides = self._preview_payload.get("slides", [])
        if slide_index < 0 or slide_index >= len(slides):
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}"
            )

        slide = slides[slide_index]
        slide_id = str(slide["slide_id"])
        slide_revision = self._slide_revision(
            slide, int(self._preview_payload["revision"])
        )
        rendered = self._renderer.get_cached(slide_id, slide_revision)
        if rendered is None:
            self._set_svg_preview()
            self._log_missing_png_cache_warning([slide_index])
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Slide preview not found: {slide_index_text}"
            )

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
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Download file not found: {filename}"
            )

        content_type, _ = mimetypes.guess_type(resolved.name)
        return (
            resolved.read_bytes(),
            content_type
            or "application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
            "deck": self._preview_deck_payload(payload),
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
    parser = argparse.ArgumentParser(
        description="Run the agent-slides live preview server."
    )
    parser.add_argument("path", help="Path to the sidecar deck JSON file.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debounce-ms", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
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
