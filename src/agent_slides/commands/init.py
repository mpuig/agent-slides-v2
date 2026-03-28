"""CLI command for creating a new deck sidecar file."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io.sidecar import init_deck
from agent_slides.model import load_design_rules
from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.themes import load_theme


@click.command("init")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--theme", "theme_name")
@click.option("--template", "template_manifest", type=click.Path(dir_okay=False, path_type=str))
@click.option("--rules", "rules_name", default="default", show_default=True)
@click.option("--force", is_flag=True, default=False)
def init_command(
    path: str,
    theme_name: str | None,
    template_manifest: str | None,
    rules_name: str,
    force: bool,
) -> None:
    """Create a new deck JSON file."""

    if theme_name is not None and template_manifest is not None:
        raise AgentSlidesError(SCHEMA_ERROR, "`--theme` and `--template` are mutually exclusive.")

    load_design_rules(rules_name)
    response_template: str | None = None

    if template_manifest is not None:
        manifest_path = Path(template_manifest)
        registry = TemplateLayoutRegistry(str(manifest_path))
        deck = init_deck(
            path,
            theme=registry.theme.name,
            design_rules=rules_name,
            force=force,
            template_manifest=str(manifest_path),
        )
        response_template = deck.template_manifest
    else:
        resolved_theme = theme_name or "default"
        load_theme(resolved_theme)
        deck = init_deck(
            path,
            theme=resolved_theme,
            design_rules=rules_name,
            force=force,
        )

    response_data: dict[str, object] = {
        "deck_id": deck.deck_id,
        "theme": deck.theme,
        "design_rules": deck.design_rules,
    }
    if response_template is not None:
        response_data["template"] = response_template

    click.echo(
        json.dumps(
            {
                "ok": True,
                "data": response_data,
            }
        )
    )
