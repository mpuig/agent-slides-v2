"""Validate command for checking a deck against design rules."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.engine.validator import validate_deck
from agent_slides.io import read_deck
from agent_slides.model.design_rules import load_design_rules


@click.command("validate")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
def validate_command(path: Path) -> None:
    """Validate a deck sidecar and emit structured warnings."""

    deck = read_deck(str(path))
    rules = load_design_rules(deck.design_rules)
    warnings = validate_deck(deck, rules)
    payload = {
        "ok": True,
        "data": {
            "warnings": [warning.model_dump(mode="json") for warning in warnings],
            "clean": not warnings,
        },
    }
    click.echo(json.dumps(payload))
