"""Built-in icon commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.icons import list_icons
from agent_slides.io import mutate_deck
from agent_slides.model import Deck
from agent_slides.model.layout_provider import LayoutProvider


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


@click.group()
def icon() -> None:
    """List and place built-in vector icons."""


@icon.command("list")
def list_icon_command() -> None:
    """List all built-in icons."""

    icons = list_icons()
    _emit_json({"ok": True, "data": {"icons": icons, "count": len(icons)}})


@icon.command("add")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--name", required=True)
@click.option("--x", type=float, required=True)
@click.option("--y", type=float, required=True)
@click.option("--size", type=float, required=True)
@click.option("--color", required=True)
def add_icon_command(
    path: str,
    slide_ref: str,
    name: str,
    x: float,
    y: float,
    size: float,
    color: str,
) -> None:
    """Place a built-in icon on a slide at absolute slide coordinates."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(
            deck,
            "icon_add",
            {
                "slide": slide_ref,
                "name": name,
                "x": x,
                "y": y,
                "size": size,
                "color": color,
            },
            provider,
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
