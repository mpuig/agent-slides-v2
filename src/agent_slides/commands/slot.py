"""Slot mutation commands."""

from __future__ import annotations

import json
from typing import Any

import click

from agent_slides.errors import AgentSlidesError, INVALID_NODE, INVALID_SLOT, SLOT_OCCUPIED
from agent_slides.io import mutate_deck
from agent_slides.model.layouts import get_layout
from agent_slides.model.types import Deck, Node, Slide


def _emit_success(data: dict[str, Any]) -> None:
    click.echo(json.dumps({"ok": True, "data": data}))


def _parse_slide_ref(ref: str) -> str | int:
    try:
        return int(ref)
    except ValueError:
        return ref


def _validate_slot(slide: Slide, slot_name: str) -> str:
    layout = get_layout(slide.layout)
    if slot_name not in layout.slots:
        valid_slots = ", ".join(sorted(layout.slots))
        raise AgentSlidesError(
            INVALID_SLOT,
            f"Slot '{slot_name}' is not valid for layout '{slide.layout}'. Valid slots: {valid_slots}",
        )
    return layout.slots[slot_name].role


def _find_slot_node(slide: Slide, slot_name: str) -> Node | None:
    for node in slide.nodes:
        if node.slot_binding == slot_name:
            return node
    return None


def _ensure_slot_node(deck: Deck, slide: Slide, slot_name: str) -> Node:
    node = _find_slot_node(slide, slot_name)
    if node is not None:
        return node

    node = Node(
        node_id=deck.next_node_id(),
        slot_binding=slot_name,
        type="text",
    )
    slide.nodes.append(node)
    return node


def _find_node(deck: Deck, node_id: str) -> tuple[Slide, Node]:
    for slide in deck.slides:
        for node in slide.nodes:
            if node.node_id == node_id:
                return slide, node

    raise AgentSlidesError(INVALID_NODE, f"Node '{node_id}' does not exist.")


@click.group()
def slot() -> None:
    """Manage content within slide slots."""


@slot.command("set")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--slide", "slide_ref", required=True, help="Slide index or slide_id.")
@click.option("--slot", "slot_name", required=True, help="Slot name in the current layout.")
@click.option("--text", required=True, help="Replacement text content.")
@click.option("--font-size", "font_size_pt", type=float, help="Fixed font size override in points.")
def slot_set(path: str, slide_ref: str, slot_name: str, text: str, font_size_pt: float | None) -> None:
    """Set the text content for a slot."""

    def mutate(deck: Deck) -> dict[str, Any]:
        slide = deck.get_slide(_parse_slide_ref(slide_ref))
        role = _validate_slot(slide, slot_name)
        node = _ensure_slot_node(deck, slide, slot_name)
        node.slot_binding = slot_name
        node.content = text
        node.style_overrides["role"] = role
        if font_size_pt is not None:
            node.style_overrides["font_size_pt"] = font_size_pt
            node.style_overrides["text_fit_disabled"] = True
        return {"slide_id": slide.slide_id, "slot": slot_name, "text": text}

    _, result = mutate_deck(path, mutate)
    _emit_success(result)


@slot.command("clear")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--slide", "slide_ref", required=True, help="Slide index or slide_id.")
@click.option("--slot", "slot_name", required=True, help="Slot name in the current layout.")
def slot_clear(path: str, slide_ref: str, slot_name: str) -> None:
    """Clear the text content for a slot."""

    def mutate(deck: Deck) -> dict[str, Any]:
        slide = deck.get_slide(_parse_slide_ref(slide_ref))
        _validate_slot(slide, slot_name)
        node = _find_slot_node(slide, slot_name)
        if node is not None:
            node.content = ""
        return {"slide_id": slide.slide_id, "slot": slot_name, "cleared": True}

    _, result = mutate_deck(path, mutate)
    _emit_success(result)


@slot.command("bind")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--node", "node_id", required=True, help="Node ID to rebind.")
@click.option("--slot", "slot_name", required=True, help="Target slot name.")
def slot_bind(path: str, node_id: str, slot_name: str) -> None:
    """Bind an existing node to a slot."""

    def mutate(deck: Deck) -> dict[str, Any]:
        slide, node = _find_node(deck, node_id)
        role = _validate_slot(slide, slot_name)
        occupied = _find_slot_node(slide, slot_name)
        if occupied is not None and occupied.node_id != node.node_id:
            raise AgentSlidesError(
                SLOT_OCCUPIED,
                (
                    f"Slot '{slot_name}' on slide '{slide.slide_id}' is already occupied "
                    f"by node '{occupied.node_id}'."
                ),
            )
        node.slot_binding = slot_name
        node.style_overrides["role"] = role
        return {"node_id": node.node_id, "slot": slot_name, "bound": True}

    _, result = mutate_deck(path, mutate)
    _emit_success(result)
