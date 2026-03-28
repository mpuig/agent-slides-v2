"""Slide collection commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.errors import UNBOUND_NODES
from agent_slides.io import mutate_deck
from agent_slides.model.layout_provider import LayoutProvider
from agent_slides.model import Deck


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

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "slide_add", {"layout": layout_name}, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slide.command("remove")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
def remove_slide_command(path: str, slide_ref: str) -> None:
    """Remove a slide by index or slide_id."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "slide_remove", {"slide": slide_ref}, provider)

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slide.command("set-layout")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--layout", "layout_name", required=True)
def set_slide_layout_command(path: str, slide_ref: str, layout_name: str) -> None:
    """Change a slide layout and rebind its slot-bound nodes."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slide_set_layout",
            {
                "slide": slide_ref,
                "layout": layout_name,
            },
            provider,
        )

    _, result = mutate_deck(path, mutate)
    _emit_warning(result["slide_id"], result["unbound_nodes"])
    _emit_json({"ok": True, "data": result})
