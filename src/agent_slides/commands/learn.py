"""Learn command for extracting a template manifest from PPTX."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.io.template_reader import read_template_manifest


@click.command("learn")
@click.argument("template_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
)
def learn_command(template_path: Path, output_path: Path | None) -> None:
    """Extract a PPTX template manifest."""

    result = read_template_manifest(template_path, output_path)
    for warning in result.warnings:
        click.echo(f"Warning: {warning}", err=True)

    click.echo(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "source": result.source,
                    "layouts_found": result.layouts_found,
                    "usable_layouts": result.usable_layouts,
                },
            }
        )
    )
