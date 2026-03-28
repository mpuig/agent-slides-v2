"""Slot content commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.io import mutate_deck
from agent_slides.model import Deck


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


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
    _emit_json({"ok": True, "data": result})


@slot.command("clear")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
def clear_slot_command(path: str, slide_ref: str, slot_name: str) -> None:
    """Remove content currently bound to a slot on a slide."""

    def mutate(deck: Deck) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slot_clear",
            {
                "slide": slide_ref,
                "slot": slot_name,
            },
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slot.command("bind")
@click.argument("path")
@click.option("--node", "node_id", required=True)
@click.option("--slot", "slot_name", required=True)
def bind_slot_command(path: str, node_id: str, slot_name: str) -> None:
    """Bind an existing node to a named slot on its slide."""

    def mutate(deck: Deck) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slot_bind",
            {
                "node": node_id,
                "slot": slot_name,
            },
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
