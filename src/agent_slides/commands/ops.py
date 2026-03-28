"""Shared deck operations used by CLI commands."""

from __future__ import annotations

import json

from agent_slides.engine.reflow import rebind_slots, reflow_deck
from agent_slides.errors import AgentSlidesError, INVALID_SLOT, SCHEMA_ERROR
from agent_slides.io import mutate_deck, read_deck, write_pptx
from agent_slides.model import Deck, Node, NodeContent, Slide, resolve_layout_provider
from agent_slides.model.layout_provider import LayoutProvider


def parse_slide_ref(value: str) -> str | int:
    try:
        return int(value)
    except ValueError:
        return value


def create_layout_nodes(deck: Deck, layout_name: str, provider: LayoutProvider) -> list[Node]:
    layout_getter = provider.get_layout
    layout = layout_getter(layout_name)
    return [
        Node(
            node_id=deck.next_node_id(),
            slot_binding=slot_name,
            type="image" if layout.slots[slot_name].role == "image" else "text",
            style_overrides={"placeholder": True} if layout.slots[slot_name].role == "image" else {},
        )
        for slot_name in layout.slots
    ]


def add_slide(path: str, layout_name: str) -> dict[str, object]:
    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        layout_getter = provider.get_layout
        layout = layout_getter(layout_name)
        slide = Slide(
            slide_id=deck.next_slide_id(),
            layout=layout.name,
            nodes=create_layout_nodes(deck, layout.name, provider),
        )
        deck.slides.append(slide)
        return {
            "slide_index": len(deck.slides) - 1,
            "slide_id": slide.slide_id,
            "layout": slide.layout,
        }

    _, result = mutate_deck(path, mutate)
    return result


def remove_slide(path: str, slide_ref: str | int) -> dict[str, object]:
    def mutate(deck: Deck, _provider: LayoutProvider) -> dict[str, object]:
        slide = deck.get_slide(slide_ref)
        deck.slides.remove(slide)
        return {
            "removed": slide.slide_id,
            "slide_count": len(deck.slides),
        }

    _, result = mutate_deck(path, mutate)
    return result


def set_slide_layout(path: str, slide_ref: str | int, layout_name: str) -> dict[str, object]:
    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        slide = deck.get_slide(slide_ref)
        unbound_nodes = rebind_slots(deck, slide, layout_name, provider)
        return {
            "slide_id": slide.slide_id,
            "layout": slide.layout,
            "unbound_nodes": unbound_nodes,
        }

    _, result = mutate_deck(path, mutate)
    return result


def _find_bound_slot_node(slide: Slide, slot_name: str) -> Node | None:
    for node in slide.nodes:
        if node.slot_binding == slot_name:
            return node
    return None


def set_slot_text(path: str, slide_ref: str | int, slot_name: str, text: str) -> dict[str, object]:
    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        slide = deck.get_slide(slide_ref)
        layout_getter = provider.get_layout
        layout = layout_getter(slide.layout)
        if slot_name not in layout.slots:
            raise AgentSlidesError(
                INVALID_SLOT,
                f"Slot '{slot_name}' is not defined for layout '{slide.layout}'.",
            )

        node = _find_bound_slot_node(slide, slot_name)
        if node is None:
            node = Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="text",
            )
            slide.nodes.append(node)

        node.content = NodeContent.from_text(text)
        return {
            "slide_id": slide.slide_id,
            "slot": slot_name,
            "node_id": node.node_id,
        }

    _, result = mutate_deck(path, mutate)
    return result


def get_deck_info(path: str) -> dict[str, object]:
    return read_deck(path).model_dump(mode="json", by_alias=True)


def build_deck_pptx(path: str, output_path: str) -> dict[str, object]:
    deck = read_deck(path)
    provider = resolve_layout_provider(deck.template_manifest)
    reflow_deck(deck, provider)
    write_pptx(deck, output_path)
    return {
        "slides": len(deck.slides),
        "output_path": output_path,
    }


def apply_batch(path: str, batch_input: str) -> list[dict[str, object]]:
    try:
        commands = json.loads(batch_input)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid batch JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    if not isinstance(commands, list):
        raise AgentSlidesError(SCHEMA_ERROR, "Batch input must be a JSON array.")

    results: list[dict[str, object]] = []
    for entry in commands:
        if not isinstance(entry, dict):
            raise AgentSlidesError(SCHEMA_ERROR, "Each batch item must be an object.")

        command = entry.get("command")
        args = entry.get("args", {})
        if not isinstance(command, str) or not isinstance(args, dict):
            raise AgentSlidesError(SCHEMA_ERROR, "Each batch item must include string command and object args.")

        if command == "slide_add":
            results.append(add_slide(path, str(args["layout"])))
        elif command == "slide_set_layout":
            results.append(
                set_slide_layout(path, args["slide"], str(args["layout"]))
            )
        elif command == "slot_set":
            results.append(
                set_slot_text(
                    path,
                    args["slide"],
                    str(args["slot"]),
                    str(args["text"]),
                )
            )
        else:
            raise AgentSlidesError(SCHEMA_ERROR, f"Unsupported batch command '{command}'.")

    return results
