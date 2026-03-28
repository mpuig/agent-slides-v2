"""CLI command for creating a new deck sidecar file."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.io.sidecar import init_deck
from agent_slides.model import load_design_rules
from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.themes import load_theme


@click.command("init")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--theme", "theme_name", default="default", show_default=True)
@click.option("--rules", "rules_name", default="default", show_default=True)
@click.option("--template", "template_manifest", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--force", is_flag=True, default=False)
def init_command(
    path: str,
    theme_name: str,
    rules_name: str,
    template_manifest: Path | None,
    force: bool,
) -> None:
    """Create a new deck JSON file."""

    load_design_rules(rules_name)
    resolved_theme = theme_name
    if template_manifest is None:
        load_theme(theme_name)
    else:
        resolved_theme = TemplateLayoutRegistry(str(template_manifest)).theme.name

    deck = init_deck(
        path,
        theme=resolved_theme,
        design_rules=rules_name,
        force=force,
        template_manifest=template_manifest,
    )

    data: dict[str, object] = {
        "deck_id": deck.deck_id,
        "theme": deck.theme,
        "design_rules": deck.design_rules,
    }
    if deck.template_manifest is not None:
        data["template_manifest"] = deck.template_manifest

    click.echo(
        json.dumps(
            {
                "ok": True,
                "data": data,
            }
        )
    )
