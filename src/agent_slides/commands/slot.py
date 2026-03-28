"""Slot content commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.io import mutate_deck
from agent_slides.model.layout_provider import LayoutProvider
from agent_slides.model import Deck


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


@click.group()
def slot() -> None:
    """Manage slot-bound content."""


def _resolve_cli_image_path(deck_path: Path, image_path: str | None) -> str | None:
    if image_path is None:
        return None

    normalized = image_path.strip()
    if not normalized:
        raise AgentSlidesError(SCHEMA_ERROR, "Option '--image' must be a non-empty path")

    candidate = Path(normalized)
    resolved = candidate if candidate.is_absolute() else (deck_path.parent / candidate)
    if not resolved.is_file():
        raise AgentSlidesError(FILE_NOT_FOUND, f"Image file not found: {resolved}")

    return normalized


@slot.command("set")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
@click.option("--text")
@click.option("--image")
def set_slot_command(path: str, slide_ref: str, slot_name: str, text: str | None, image: str | None) -> None:
    """Set text or image content for a slot on a slide."""

    if (text is None) == (image is None):
        raise AgentSlidesError(
            SCHEMA_ERROR,
            "Options '--text' and '--image' are mutually exclusive; provide exactly one",
        )

    image_path = _resolve_cli_image_path(Path(path), image)

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        args: dict[str, object] = {
            "slide": slide_ref,
            "slot": slot_name,
        }
        if text is not None:
            args["text"] = text
        if image_path is not None:
            args["image"] = image_path

        return apply_mutation(
            deck,
            "slot_set",
            args,
            provider,
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slot.command("clear")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
def clear_slot_command(path: str, slide_ref: str, slot_name: str) -> None:
    """Remove content currently bound to a slot on a slide."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slot_clear",
            {
                "slide": slide_ref,
                "slot": slot_name,
            },
            provider,
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slot.command("bind")
@click.argument("path")
@click.option("--node", "node_id", required=True)
@click.option("--slot", "slot_name", required=True)
def bind_slot_command(path: str, node_id: str, slot_name: str) -> None:
    """Bind an existing node to a named slot on its slide."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slot_bind",
            {
                "node": node_id,
                "slot": slot_name,
            },
            provider,
        )

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
