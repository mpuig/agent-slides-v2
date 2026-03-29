"""Slot content commands."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.commands.warnings import attach_layout_fallback_warning
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.io import mutate_deck
from agent_slides.model.layout_provider import LayoutProvider
from agent_slides.model import Deck, NodeContent


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

    deck_dir = deck_path.parent.resolve()
    candidate = Path(normalized).expanduser()
    resolved = candidate if candidate.is_absolute() else (deck_dir / candidate)
    if not resolved.is_file():
        raise AgentSlidesError(FILE_NOT_FOUND, f"Image file not found: {resolved}")

    if candidate.is_absolute():
        return Path(os.path.relpath(resolved.resolve(), deck_dir)).as_posix()

    return normalized


def _parse_content_json(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON for '--content': {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    try:
        return NodeContent.model_validate(payload).model_dump(mode="json")
    except Exception as exc:
        raise AgentSlidesError(SCHEMA_ERROR, "Argument '--content' must be valid structured text") from exc


@slot.command("set")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
@click.option("--text")
@click.option("--content", "content_json")
@click.option("--image")
def set_slot_command(
    path: str,
    slide_ref: str,
    slot_name: str,
    text: str | None,
    content_json: str | None,
    image: str | None,
) -> None:
    """Set text, structured content, or image content for a slot on a slide."""

    provided_count = sum(value is not None for value in (text, content_json, image))
    if provided_count != 1:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            "Options '--text', '--content', and '--image' are mutually exclusive; provide exactly one",
        )

    image_path = _resolve_cli_image_path(Path(path), image)
    content = _parse_content_json(content_json) if content_json is not None else None

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        args: dict[str, object] = {
            "slide": slide_ref,
            "slot": slot_name,
        }
        if text is not None:
            args["text"] = text
        if content is not None:
            args["content"] = content
        if image_path is not None:
            args["image"] = image_path

        return apply_mutation(
            deck,
            "slot_set",
            args,
            provider,
        )

    deck, result = mutate_deck(path, mutate)
    _emit_json(
        attach_layout_fallback_warning(
            {"ok": True, "data": result},
            deck,
            slide_ids=[str(result["slide_id"])],
        )
    )


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

    deck, result = mutate_deck(path, mutate)
    _emit_json(
        attach_layout_fallback_warning(
            {"ok": True, "data": result},
            deck,
            slide_ids=[str(result["slide_id"])],
        )
    )


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

    deck, result = mutate_deck(path, mutate)
    _emit_json(attach_layout_fallback_warning({"ok": True, "data": result}, deck))
