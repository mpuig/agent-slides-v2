"""Info command for dumping the full deck JSON."""

from __future__ import annotations

from pathlib import Path

import click

from agent_slides.io import read_deck


@click.command("info")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
def info_command(path: Path) -> None:
    """Dump the full deck sidecar JSON with indentation."""

    deck = read_deck(str(path))
    click.echo(deck.model_dump_json(by_alias=True, indent=2))
