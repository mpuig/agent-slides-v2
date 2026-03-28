"""Slide collection commands."""

from __future__ import annotations

import json

import click

from agent_slides.engine.reflow import rebind_slots
from agent_slides.errors import UNBOUND_NODES
from agent_slides.io import mutate_deck
from agent_slides.model import Deck, Node, Slide, get_layout


def _parse_slide_ref(value: str) -> str | int:
    try:
        return int(value)
    except ValueError:
        return value


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


def _create_slot_nodes(deck: Deck, layout_name: str) -> Slide:
    layout = get_layout(layout_name)
    return Slide(
        slide_id=deck.next_slide_id(),
        layout=layout.name,
        nodes=[
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="text",
            )
            for slot_name in layout.slots
        ],
    )


@click.group()
def slide() -> None:
    """Manage deck slides."""


@slide.command("add")
@click.argument("path")
@click.option("--layout", "layout_name", required=True)
def add_slide(path: str, layout_name: str) -> None:
    """Append a slide using a named layout."""

    layout = get_layout(layout_name)

    def mutate(deck: Deck) -> dict[str, object]:
        slide = _create_slot_nodes(deck, layout.name)
        deck.slides.append(slide)
        return {
            "slide_index": len(deck.slides) - 1,
            "slide_id": slide.slide_id,
            "layout": slide.layout,
        }

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slide.command("remove")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
def remove_slide(path: str, slide_ref: str) -> None:
    """Remove a slide by index or slide_id."""

    ref = _parse_slide_ref(slide_ref)

    def mutate(deck: Deck) -> dict[str, object]:
        target = deck.get_slide(ref)
        deck.slides.remove(target)
        return {
            "removed": target.slide_id,
            "slide_count": len(deck.slides),
        }

    _, result = mutate_deck(path, mutate)
    _emit_json({"ok": True, "data": result})


@slide.command("set-layout")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--layout", "layout_name", required=True)
def set_slide_layout(path: str, slide_ref: str, layout_name: str) -> None:
    """Change a slide layout and rebind its slot-bound nodes."""

    ref = _parse_slide_ref(slide_ref)
    layout = get_layout(layout_name)

    def mutate(deck: Deck) -> dict[str, object]:
        target = deck.get_slide(ref)
        unbound_nodes = rebind_slots(deck, target, layout)
        return {
            "slide_id": target.slide_id,
            "layout": target.layout,
            "unbound_nodes": unbound_nodes,
        }

    _, result = mutate_deck(path, mutate)
    _emit_warning(result["slide_id"], result["unbound_nodes"])
    _emit_json({"ok": True, "data": result})

