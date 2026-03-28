"""Info command for inspecting the sidecar deck."""

from __future__ import annotations

import json

import click

from agent_slides.commands.ops import get_deck_info


@click.command("info")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
def info_command(path: str) -> None:
    """Print the current deck JSON."""

    click.echo(json.dumps(get_deck_info(path)))
