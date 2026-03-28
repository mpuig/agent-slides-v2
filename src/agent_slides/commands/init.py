"""CLI command for creating a new deck sidecar file."""

from __future__ import annotations

import json

import click

from agent_slides.io.sidecar import init_deck
from agent_slides.model import load_design_rules
from agent_slides.model.themes import load_theme


@click.command("init")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--theme", "theme_name", default="default", show_default=True)
@click.option("--rules", "rules_name", default="default", show_default=True)
@click.option("--force", is_flag=True, default=False)
def init_command(path: str, theme_name: str, rules_name: str, force: bool) -> None:
    """Create a new deck JSON file."""

    load_theme(theme_name)
    load_design_rules(rules_name)

    deck = init_deck(
        path,
        theme=theme_name,
        design_rules=rules_name,
        force=force,
    )

    click.echo(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "deck_id": deck["deck_id"],
                    "theme": deck["theme"],
                    "design_rules": deck["design_rules"],
                },
            }
        )
    )
