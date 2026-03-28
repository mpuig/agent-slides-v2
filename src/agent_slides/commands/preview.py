"""CLI command for running the live preview server."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import tempfile
import webbrowser
from pathlib import Path

import click

from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io import read_deck
from agent_slides.preview import PreviewServer


_BACKGROUND_STARTUP_TIMEOUT_SECONDS = 5.0


def _wait_for_shutdown() -> None:
    while True:
        time.sleep(1)


def _write_ready_file(path: Path, payload: dict[str, object]) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(path)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _spawn_background_preview(path: Path, *, port: int) -> dict[str, object]:
    ready_fd, ready_name = tempfile.mkstemp(prefix="agent-slides-preview-ready-", suffix=".json")
    error_fd, error_name = tempfile.mkstemp(prefix="agent-slides-preview-error-", suffix=".log")
    os.close(ready_fd)
    os.close(error_fd)

    ready_path = Path(ready_name)
    error_path = Path(error_name)
    _safe_unlink(ready_path)
    command = [
        sys.executable,
        "-m",
        "agent_slides",
        "preview",
        str(path),
        "--port",
        str(port),
        "--no-open",
        "--ready-file",
        str(ready_path),
    ]

    with open(os.devnull, "r", encoding="utf-8") as stdin_stream, open(
        os.devnull,
        "w",
        encoding="utf-8",
    ) as stdout_stream, open(error_path, "w", encoding="utf-8") as stderr_stream:
        process = subprocess.Popen(
            command,
            stdin=stdin_stream,
            stdout=stdout_stream,
            stderr=stderr_stream,
            start_new_session=True,
        )

    started_payload: dict[str, object] | None = None
    deadline = time.monotonic() + _BACKGROUND_STARTUP_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            if ready_path.exists() and ready_path.stat().st_size > 0:
                started_payload = json.loads(ready_path.read_text(encoding="utf-8"))
                break
            if process.poll() is not None:
                message = error_path.read_text(encoding="utf-8").strip()
                if not message:
                    message = f"Preview background process exited with code {process.returncode}."
                raise AgentSlidesError(SCHEMA_ERROR, message)
            time.sleep(0.05)

        if started_payload is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            raise AgentSlidesError(SCHEMA_ERROR, "Preview server did not start within 5 seconds.")

        return {
            "url": started_payload["url"],
            "pid": process.pid,
        }
    finally:
        _safe_unlink(ready_path)
        _safe_unlink(error_path)


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
@click.option("--background", is_flag=True, default=False)
@click.option("--ready-file", type=click.Path(dir_okay=False, path_type=Path), hidden=True)
def preview_command(
    path: Path,
    port: int,
    no_open: bool,
    background: bool,
    ready_file: Path | None,
) -> None:
    """Start the live preview HTTP and WebSocket server."""

    read_deck(str(path))
    if background:
        result = _spawn_background_preview(path, port=port)
        if not no_open:
            try:
                webbrowser.open(str(result["url"]))
            except Exception:
                pass
        click.echo(json.dumps({"ok": True, "data": result}))
        return

    server = _ForegroundPreviewServer(path, port=port)
    server.start()

    try:
        startup_payload = {
            "url": server.url,
            "watching": path.name,
        }
        if ready_file is not None:
            _write_ready_file(ready_file, startup_payload)
        if not no_open:
            try:
                webbrowser.open(server.url)
            except Exception:
                pass

        click.echo(
            json.dumps(
                {
                    "ok": True,
                    "data": startup_payload,
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
