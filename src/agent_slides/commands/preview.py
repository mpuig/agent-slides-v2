"""CLI command for running the live preview server."""

from __future__ import annotations

import asyncio

import click

from agent_slides.preview import run_preview_server


@click.command("preview")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--host", default="localhost", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--debounce-ms", type=int, default=50, show_default=True)
def preview_command(path: str, host: str, port: int, debounce_ms: int) -> None:
    """Run the live preview HTTP and WebSocket server."""

    asyncio.run(
        run_preview_server(
            path,
            host=host,
            port=port,
            debounce_ms=debounce_ms,
        )
    )
