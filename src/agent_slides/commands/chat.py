"""CLI command for running the chat-mode preview server."""

from __future__ import annotations

import importlib.util
import json
import os
import webbrowser
from pathlib import Path

import click

from agent_slides.commands.preview import _ForegroundPreviewServer, _wait_for_shutdown
from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io import init_deck
from agent_slides.model import load_design_rules
from agent_slides.model.themes import load_theme
from agent_slides.preview import DeckOrchestrator


def _require_api_key() -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    raise AgentSlidesError(
        SCHEMA_ERROR,
        "Chat mode requires `ANTHROPIC_API_KEY`. Set the environment variable and try again.",
    )


def _require_anthropic_dependency() -> None:
    if importlib.util.find_spec("anthropic") is not None:
        return

    raise AgentSlidesError(
        SCHEMA_ERROR,
        "Chat mode requires: pip install agent-slides[chat]",
    )


def _ensure_deck_exists(path: Path) -> None:
    if path.exists():
        return

    load_design_rules("default")
    load_theme("default")
    init_deck(str(path), theme="default", design_rules="default", force=False)


@click.command("chat")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--no-open", is_flag=True, default=False)
def chat_command(path: Path, port: int, no_open: bool) -> None:
    """Start the chat-mode preview HTTP server."""

    api_key = _require_api_key()
    _require_anthropic_dependency()
    _ensure_deck_exists(path)

    server = _ForegroundPreviewServer(
        path,
        port=port,
        mode="chat",
        orchestrator=DeckOrchestrator(path, api_key),
    )
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
                        "mode": "chat",
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
