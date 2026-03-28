"""Shape commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.io import mutate_deck
from agent_slides.model import Deck
from agent_slides.model.layout_provider import LayoutProvider


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload))


@click.group()
def shape() -> None:
    """Manage slide-level shape primitives."""


@shape.command("add")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--type", "shape_type", required=True)
@click.option("--x", required=True)
@click.option("--y", required=True)
@click.option("--w", required=True)
@click.option("--h", required=True)
@click.option("--fill")
@click.option("--color")
@click.option("--line-color", "line_color")
@click.option("--line-width", "line_width")
@click.option("--corner-radius", "corner_radius")
@click.option("--shadow/--no-shadow", default=False)
@click.option("--dash")
@click.option("--opacity")
@click.option("--z-index", "z_index")
def add_shape_command(
    path: str,
    slide_ref: str,
    shape_type: str,
    x: str,
    y: str,
    w: str,
    h: str,
    fill: str | None,
    color: str | None,
    line_color: str | None,
    line_width: str | None,
    corner_radius: str | None,
    shadow: bool,
    dash: str | None,
    opacity: str | None,
    z_index: str | None,
) -> None:
    """Add a decorative or structural shape to a slide."""

    mutation_args: dict[str, object] = {
        "slide": slide_ref,
        "type": shape_type,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "shadow": shadow,
    }
    if fill is not None:
        mutation_args["fill"] = fill
    if color is not None:
        mutation_args["color"] = color
    if line_color is not None:
        mutation_args["line_color"] = line_color
    if line_width is not None:
        mutation_args["line_width"] = line_width
    if corner_radius is not None:
        mutation_args["corner_radius"] = corner_radius
    if dash is not None:
        mutation_args["dash"] = dash
    if opacity is not None:
        mutation_args["opacity"] = opacity
    if z_index is not None:
        mutation_args["z_index"] = z_index

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "shape_add", mutation_args, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})
