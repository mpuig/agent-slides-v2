"""Slot content commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.io import mutate_deck
from agent_slides.model import Deck


@click.group()
def slot() -> None:
    """Manage slot-bound content."""


@slot.command("set")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
@click.option("--text", required=True)
def set_slot_command(path: str, slide_ref: str, slot_name: str, text: str) -> None:
    """Set text content for a slot on a slide."""

    def mutate(deck: Deck) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slot_set",
            {
                "slide": slide_ref,
                "slot": slot_name,
                "text": text,
            },
        )

    _, result = mutate_deck(path, mutate)
    click.echo(json.dumps({"ok": True, "data": result}))
