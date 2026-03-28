"""Pattern commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.io import mutate_deck
from agent_slides.model import Deck
from agent_slides.model.layout_provider import LayoutProvider


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


def _parse_pattern_json(raw: str, *, option_name: str) -> dict[str, Any] | list[Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON for '{option_name}': {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    if not isinstance(payload, dict | list):
        raise AgentSlidesError(SCHEMA_ERROR, f"Argument '{option_name}' must be a JSON object or array")
    return payload


def _load_pattern_data(data_json: str | None, data_file: str | None) -> dict[str, Any] | list[Any]:
    if (data_json is None) == (data_file is None):
        raise AgentSlidesError(SCHEMA_ERROR, "Exactly one of '--data' or '--data-file' is required")

    if data_json is not None:
        return _parse_pattern_json(data_json, option_name="--data")

    assert data_file is not None
    data_path = Path(data_file)
    try:
        payload = data_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Pattern data file not found: {data_path}") from exc
    except OSError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Failed to read pattern data file {data_path}: {exc.strerror or str(exc)}",
        ) from exc

    return _parse_pattern_json(payload, option_name="--data-file")


@click.group()
def pattern() -> None:
    """Manage slot-bound freeform composition patterns."""


@pattern.command("add")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--type", "pattern_type", required=True)
@click.option("--slot", "slot_name")
@click.option("--columns", type=int)
@click.option("--data", "data_json")
@click.option("--data-file", "data_file")
def add_pattern_command(
    path: str,
    slide_ref: str,
    pattern_type: str,
    slot_name: str | None,
    columns: int | None,
    data_json: str | None,
    data_file: str | None,
) -> None:
    """Create or replace a slot-bound pattern node in a slide."""

    mutation_args: dict[str, object] = {
        "slide": slide_ref,
        "type": pattern_type,
        "data": _load_pattern_data(data_json, data_file),
    }
    if slot_name is not None:
        mutation_args["slot"] = slot_name
    if columns is not None:
        mutation_args["columns"] = columns

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "pattern_add", mutation_args, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
