"""Slide collection commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.ops import (
    add_slide,
    parse_slide_ref,
    remove_slide,
    set_slide_layout,
)
from agent_slides.errors import UNBOUND_NODES


def _emit_json(payload: dict[str, object], *, err: bool = False) -> None:
    click.echo(json.dumps(payload), err=err)


def _emit_warning(slide_id: str, unbound_nodes: list[str]) -> None:
    if not unbound_nodes:
        return

    _emit_json(
        {
            "ok": True,
            "warning": {
                "code": UNBOUND_NODES,
                "message": f"{len(unbound_nodes)} node(s) became unbound during slot rebinding.",
            },
            "data": {
                "slide_id": slide_id,
                "unbound_nodes": unbound_nodes,
            },
        },
        err=True,
    )
@click.group()
def slide() -> None:
    """Manage deck slides."""


@slide.command("add")
@click.argument("path")
@click.option("--layout", "layout_name", required=True)
def add_slide_command(path: str, layout_name: str) -> None:
    """Append a slide using a named layout."""

    _emit_json({"ok": True, "data": add_slide(path, layout_name)})


@slide.command("remove")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
def remove_slide_command(path: str, slide_ref: str) -> None:
    """Remove a slide by index or slide_id."""

    _emit_json({"ok": True, "data": remove_slide(path, parse_slide_ref(slide_ref))})


@slide.command("set-layout")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--layout", "layout_name", required=True)
def set_slide_layout_command(path: str, slide_ref: str, layout_name: str) -> None:
    """Change a slide layout and rebind its slot-bound nodes."""

    result = set_slide_layout(path, parse_slide_ref(slide_ref), layout_name)
    if result["unbound_nodes"]:
        _emit_json(
            {
                "ok": True,
                "warning": {
                    "code": UNBOUND_NODES,
                    "message": f"{len(result['unbound_nodes'])} node(s) became unbound during slot rebinding.",
                },
                "data": {
                    "slide_id": result["slide_id"],
                    "unbound_nodes": result["unbound_nodes"],
                },
            },
            err=True,
        )
    _emit_json({"ok": True, "data": result})
