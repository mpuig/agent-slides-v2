"""Chart commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io import mutate_deck
from agent_slides.model import Deck
from agent_slides.model.layout_provider import LayoutProvider


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


def _parse_chart_spec_json(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON for '--spec': {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    if not isinstance(payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Argument '--spec' must be a JSON object")
    return payload


@click.group()
def chart() -> None:
    """Manage slot-bound charts."""


@chart.command("add")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
@click.option("--spec", "spec_json", required=True)
def add_chart_command(path: str, slide_ref: str, slot_name: str, spec_json: str) -> None:
    """Create or replace the chart bound to a slot on a slide."""

    mutation_args = {
        "slide": slide_ref,
        "slot": slot_name,
        "chart_spec": _parse_chart_spec_json(spec_json),
    }

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "chart_add", mutation_args, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@chart.command("update")
@click.argument("path")
@click.option("--node", "node_id", required=True)
@click.option("--spec", "spec_json", required=True)
def update_chart_command(path: str, node_id: str, spec_json: str) -> None:
    """Update the chart specification for an existing chart node."""

    mutation_args = {
        "node": node_id,
        "chart_spec": _parse_chart_spec_json(spec_json),
    }

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "chart_update", mutation_args, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
