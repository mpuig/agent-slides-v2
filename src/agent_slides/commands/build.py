"""Build a PPTX from a deck sidecar."""

from __future__ import annotations

import json

import click

from agent_slides.commands.ops import build_deck_pptx


@click.command("build")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(dir_okay=False, path_type=str))
def build_command(path: str, output_path: str) -> None:
    """Render the deck to a PowerPoint file."""

    click.echo(json.dumps({"ok": True, "data": build_deck_pptx(path, output_path)}))
