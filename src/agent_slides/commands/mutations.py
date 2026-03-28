"""Shared deck mutation helpers for CLI commands."""

from __future__ import annotations

from typing import Any

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT, INVALID_SLOT, SCHEMA_ERROR
from agent_slides.model import Deck, Node, Slide

SUPPORTED_LAYOUTS: dict[str, set[str]] = {
    "title": {"title", "subtitle"},
    "two_col": {"title", "left", "right"},
    "content": {"title", "body"},
    "body": {"body"},
    "closing": {"title", "body"},
}

SUPPORTED_MUTATION_COMMANDS = frozenset(
    {
        "slide_add",
        "slide_remove",
        "slide_set_layout",
        "slot_set",
        "slot_clear",
        "slot_bind",
    }
)


def _normalize_slide_ref(ref: Any) -> str | int:
    if isinstance(ref, bool):
        raise AgentSlidesError(SCHEMA_ERROR, f"Slide reference must be an int or string, got {type(ref).__name__}")
    if isinstance(ref, int):
        return ref
    if isinstance(ref, str):
        stripped = ref.strip()
        if stripped.startswith("-") and stripped[1:].isdigit():
            return int(stripped)
        if stripped.isdigit():
            return int(stripped)
        if stripped:
            return stripped
    raise AgentSlidesError(SCHEMA_ERROR, f"Slide reference must be an int or string, got {type(ref).__name__}")


def _require_string(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentSlidesError(SCHEMA_ERROR, f"Argument '{key}' must be a non-empty string")
    return value


def _require_layout(layout: str) -> str:
    normalized = layout.strip()
    if normalized not in SUPPORTED_LAYOUTS:
        supported = ", ".join(sorted(SUPPORTED_LAYOUTS))
        raise AgentSlidesError(
            INVALID_LAYOUT,
            f"Unsupported layout {normalized!r}. Supported layouts: {supported}",
        )
    return normalized


def _slide_index(deck: Deck, slide: Slide) -> int:
    return deck.slides.index(slide)


def _require_slot(slide: Slide, slot: str) -> str:
    normalized = slot.strip()
    allowed = SUPPORTED_LAYOUTS.get(slide.layout)
    if allowed is None:
        raise AgentSlidesError(INVALID_LAYOUT, f"Slide {slide.slide_id!r} uses unsupported layout {slide.layout!r}")
    if normalized not in allowed:
        allowed_slots = ", ".join(sorted(allowed))
        raise AgentSlidesError(
            INVALID_SLOT,
            f"Slot {normalized!r} is not valid for layout {slide.layout!r}. Allowed slots: {allowed_slots}",
        )
    return normalized


def _find_slot_nodes(slide: Slide, slot: str) -> list[Node]:
    return [node for node in slide.nodes if node.slot_binding == slot]


def _prune_nodes(slide: Slide, node_ids: set[str]) -> None:
    if not node_ids:
        return
    slide.nodes = [node for node in slide.nodes if node.node_id not in node_ids]
    for node_id in node_ids:
        slide.computed.pop(node_id, None)


def _find_node(deck: Deck, node_id: str) -> tuple[Slide, Node]:
    for slide in deck.slides:
        for node in slide.nodes:
            if node.node_id == node_id:
                return slide, node
    raise AgentSlidesError(SCHEMA_ERROR, f"Node {node_id!r} does not exist")


def apply_mutation(deck: Deck, command: str, args: dict[str, Any]) -> dict[str, Any]:
    """Apply one supported mutation and return its structured result."""

    if command == "slide_add":
        layout = _require_layout(_require_string(args, "layout"))
        slide = Slide(slide_id=deck.next_slide_id(), layout=layout)
        deck.slides.append(slide)
        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": _slide_index(deck, slide),
            "layout": slide.layout,
        }

    if command == "slide_remove":
        slide_ref = _normalize_slide_ref(args.get("slide"))
        slide = deck.get_slide(slide_ref)
        removed_index = _slide_index(deck, slide)
        deck.slides.pop(removed_index)
        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": removed_index,
            "layout": slide.layout,
        }

    if command == "slide_set_layout":
        slide_ref = _normalize_slide_ref(args.get("slide"))
        layout = _require_layout(_require_string(args, "layout"))
        slide = deck.get_slide(slide_ref)
        slide.layout = layout
        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": _slide_index(deck, slide),
            "layout": slide.layout,
        }

    if command == "slot_set":
        slide_ref = _normalize_slide_ref(args.get("slide"))
        slot = _require_string(args, "slot")
        text = args.get("text")
        if not isinstance(text, str):
            raise AgentSlidesError(SCHEMA_ERROR, "Argument 'text' must be a string")

        slide = deck.get_slide(slide_ref)
        slot_name = _require_slot(slide, slot)
        slot_nodes = _find_slot_nodes(slide, slot_name)

        if slot_nodes:
            node = slot_nodes[0]
            _prune_nodes(slide, {extra.node_id for extra in slot_nodes[1:]})
        else:
            node = Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="text",
            )
            slide.nodes.append(node)

        node.slot_binding = slot_name
        node.content = text

        if "font_size" in args:
            font_size = args["font_size"]
            if font_size is None:
                node.style_overrides.pop("font_size", None)
            elif isinstance(font_size, bool) or not isinstance(font_size, int | float):
                raise AgentSlidesError(SCHEMA_ERROR, "Argument 'font_size' must be a number")
            else:
                node.style_overrides["font_size"] = float(font_size)

        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": _slide_index(deck, slide),
            "slot": slot_name,
            "node_id": node.node_id,
            "text": node.content,
            "font_size": node.style_overrides.get("font_size"),
        }

    if command == "slot_clear":
        slide_ref = _normalize_slide_ref(args.get("slide"))
        slot = _require_string(args, "slot")
        slide = deck.get_slide(slide_ref)
        slot_name = _require_slot(slide, slot)
        removed_ids = [node.node_id for node in _find_slot_nodes(slide, slot_name)]
        _prune_nodes(slide, set(removed_ids))
        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": _slide_index(deck, slide),
            "slot": slot_name,
            "removed_node_ids": removed_ids,
        }

    if command == "slot_bind":
        node_id = _require_string(args, "node")
        slot = _require_string(args, "slot")
        slide, node = _find_node(deck, node_id)
        slot_name = _require_slot(slide, slot)

        conflicting_nodes = [
            candidate
            for candidate in _find_slot_nodes(slide, slot_name)
            if candidate.node_id != node.node_id
        ]
        _prune_nodes(slide, {candidate.node_id for candidate in conflicting_nodes})
        node.slot_binding = slot_name

        return {
            "command": command,
            "slide_id": slide.slide_id,
            "slide_index": _slide_index(deck, slide),
            "slot": slot_name,
            "node_id": node.node_id,
        }

    raise AgentSlidesError(
        SCHEMA_ERROR,
        f"Unsupported mutation command {command!r}. Supported commands: {', '.join(sorted(SUPPORTED_MUTATION_COMMANDS))}",
    )
