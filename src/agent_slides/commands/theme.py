"""Theme management commands."""

from __future__ import annotations

import json

import click

from agent_slides.io import mutate_deck
from agent_slides.model import Deck
from agent_slides.model.themes import list_themes, load_theme


@click.group()
def theme() -> None:
    """List and apply deck themes."""


@theme.command("list")
def list_theme_command() -> None:
    """List all built-in themes."""

    click.echo(json.dumps({"ok": True, "data": {"themes": list_themes()}}))


@theme.command("apply")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--theme", "theme_name", required=True)
def apply_theme_command(path: str, theme_name: str) -> None:
    """Switch an existing deck to a different built-in theme."""

    load_theme(theme_name)

    def mutate(deck: Deck) -> dict[str, str]:
        previous = deck.theme
        deck.theme = theme_name
        return {
            "theme": deck.theme,
            "previous": previous,
        }

    _, result = mutate_deck(path, mutate)
    click.echo(json.dumps({"ok": True, "data": result}))
