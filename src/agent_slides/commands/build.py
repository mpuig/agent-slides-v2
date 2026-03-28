"""Build command for rendering a deck sidecar into a PPTX file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import click

from agent_slides.engine.reflow import reflow_deck
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, TEMPLATE_CHANGED
from agent_slides.io import read_deck, resolve_manifest_path, write_computed_deck, write_pptx
from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.layout_provider import resolve_layout_provider


def _emit_warning(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload), err=True)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Template file not found: {path}") from exc


def _warn_if_template_changed(provider: object) -> None:
    if not isinstance(provider, TemplateLayoutRegistry):
        return

    source_path = Path(provider.source_path)
    actual_hash = _sha256(source_path)
    if actual_hash == provider.source_hash:
        return

    _emit_warning(
        {
            "ok": True,
            "warning": {
                "code": TEMPLATE_CHANGED,
                "message": "Template source file changed since the manifest was learned.",
            },
            "data": {
                "template": str(source_path),
                "expected_hash": provider.source_hash,
                "actual_hash": actual_hash,
            },
        }
    )


@click.command("build")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def build_command(path: Path, output_path: Path) -> None:
    """Build a PPTX file from a deck sidecar."""

    deck = read_deck(str(path))
    provider = resolve_layout_provider(resolve_manifest_path(str(path), deck))
    reflow_deck(deck, provider)
    write_computed_deck(str(path), deck)
    _warn_if_template_changed(provider)
    write_pptx(deck, str(output_path), provider=provider)
    payload = {
        "ok": True,
        "data": {
            "output": str(output_path),
            "slides": len(deck.slides),
        },
    }
    click.echo(json.dumps(payload))
