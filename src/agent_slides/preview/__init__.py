"""Live preview server components."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from agent_slides.preview.orchestrator import ChatResponse, DeckOrchestrator
from agent_slides.preview.server import PreviewServer, run_preview_server
from agent_slides.preview.watcher import SidecarWatcher


def client_html_path() -> Path:
    """Return the packaged preview client HTML path."""

    return Path(str(files("agent_slides.preview").joinpath("client.html")))


def chat_html_path() -> Path:
    """Return the packaged preview chat HTML path."""

    return Path(str(files("agent_slides.preview").joinpath("chat.html")))


def read_client_html() -> str:
    """Read the packaged preview client HTML."""

    return client_html_path().read_text(encoding="utf-8")


def read_chat_html() -> str:
    """Read the packaged preview chat HTML."""

    return chat_html_path().read_text(encoding="utf-8")


__all__ = [
    "ChatResponse",
    "DeckOrchestrator",
    "PreviewServer",
    "SidecarWatcher",
    "chat_html_path",
    "client_html_path",
    "read_chat_html",
    "read_client_html",
    "run_preview_server",
]
