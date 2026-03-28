"""CLI entry point for the live preview server."""

from __future__ import annotations

import json
import time
import webbrowser
from pathlib import Path

import click

from agent_slides.io import read_deck
from agent_slides.preview import PreviewServer


def _wait_for_shutdown() -> None:
    while True:
        time.sleep(1)


@click.command("preview")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--no-open", is_flag=True, default=False)
def preview_command(path: Path, port: int, no_open: bool) -> None:
    """Start the live preview server in the foreground."""

    read_deck(str(path))
    server = PreviewServer(path, port=port)
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
