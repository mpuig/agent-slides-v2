"""Build command for rendering a deck sidecar into a PPTX file."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.engine.reflow import reflow_deck
from agent_slides.io import read_deck, write_computed_deck, write_pptx
from agent_slides.model.layout_provider import resolve_layout_provider


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
    provider = resolve_layout_provider(deck.template_manifest)
    reflow_deck(deck, provider)
    write_computed_deck(str(path), deck)
    write_pptx(deck, str(output_path))
    payload = {
        "ok": True,
        "data": {
            "output": str(output_path),
            "slides": len(deck.slides),
        },
    }
    click.echo(json.dumps(payload))
