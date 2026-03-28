"""CLI command for running the live preview server."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from pathlib import Path

import click

from agent_slides.io import read_deck
from agent_slides.preview import PreviewServer


def _wait_for_shutdown() -> None:
    while True:
        time.sleep(1)


class _ForegroundPreviewServer:
    def __init__(
        self,
        path: Path,
        *,
        port: int,
    ) -> None:
        self._server = PreviewServer(
            str(path),
            port=port,
        )
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._ready = threading.Event()
        self._startup_error: Exception | None = None

    @property
    def url(self) -> str:
        return self._server.origin

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="agent-slides-preview", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Preview server did not start within 5 seconds.")
        if self._startup_error is not None:
            raise self._startup_error

    def stop(self) -> None:
        if self._loop is None or self._stop_event is None:
            return

        self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._stop_event = asyncio.Event()
        asyncio.set_event_loop(self._loop)

        async def serve() -> None:
            try:
                await self._server.start()
                self._ready.set()
                await self._stop_event.wait()
            except Exception as exc:  # pragma: no cover - surfaced through start()
                self._startup_error = exc
                self._ready.set()
            finally:
                await self._server.stop()

        self._loop.run_until_complete(serve())
        self._loop.close()


@click.command("preview")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--no-open", is_flag=True, default=False)
def preview_command(path: Path, port: int, no_open: bool) -> None:
    """Start the live preview HTTP and WebSocket server."""

    read_deck(str(path))
    server = _ForegroundPreviewServer(path, port=port)
    server.start()

    try:
        if not no_open:
            try:
                webbrowser.open(server.url)
            except Exception:
                pass

        click.echo(
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "url": server.url,
                        "watching": path.name,
                    },
                }
            )
        )

        try:
            _wait_for_shutdown()
        except KeyboardInterrupt:
            pass
    finally:
        server.stop()
        click.echo(json.dumps({"ok": True, "data": {"stopped": True}}))
