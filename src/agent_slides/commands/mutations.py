"""Shared deck mutation helpers for CLI commands."""

from __future__ import annotations

from typing import Any

from agent_slides.engine.reflow import rebind_slots
from agent_slides.errors import AgentSlidesError, INVALID_SLOT, SCHEMA_ERROR
from agent_slides.model import Deck, Node, NodeContent, Slide, get_layout

SLOT_ALIASES = {
    "title": "heading",
    "subtitle": "subheading",
    "left": "col1",
    "right": "col2",
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
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Slide reference must be an int or string, got {type(ref).__name__}",
        )
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
    raise AgentSlidesError(
        SCHEMA_ERROR,
        f"Slide reference must be an int or string, got {type(ref).__name__}",
    )


def _require_string(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentSlidesError(SCHEMA_ERROR, f"Argument '{key}' must be a non-empty string")
    return value.strip()


def _create_slot_nodes(deck: Deck, layout_name: str) -> Slide:
    layout = get_layout(layout_name)
    return Slide(
        slide_id=deck.next_slide_id(),
        layout=layout.name,
        nodes=[
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="image" if layout.slots[slot_name].role == "image" else "text",
            )
            for slot_name in layout.slots
        ],
    )


def _resolve_slot_name(slide: Slide, slot: str) -> str:
    layout = get_layout(slide.layout)
    normalized = SLOT_ALIASES.get(slot.strip(), slot.strip())
    if normalized not in layout.slots:
        allowed = ", ".join(layout.slots)
        raise AgentSlidesError(
            INVALID_SLOT,
            f"Slot {slot!r} is not valid for layout {slide.layout!r}. Allowed slots: {allowed}",
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


def _coerce_content(args: dict[str, Any]) -> NodeContent:
    if "content" in args:
        try:
            return NodeContent.model_validate(args["content"])
        except Exception as exc:
            raise AgentSlidesError(SCHEMA_ERROR, "Argument 'content' must be valid structured text") from exc

    text = args.get("text")
    if not isinstance(text, str):
        raise AgentSlidesError(SCHEMA_ERROR, "Argument 'text' must be a string")
    return NodeContent.from_text(text)


def apply_mutation(deck: Deck, command: str, args: dict[str, Any]) -> dict[str, Any]:
    """Apply one supported mutation and return its structured result."""

    if command == "slide_add":
        slide = _create_slot_nodes(deck, _require_string(args, "layout"))
        deck.slides.append(slide)
        return {
            "slide_index": len(deck.slides) - 1,
            "slide_id": slide.slide_id,
            "layout": slide.layout,
        }

    if command == "slide_remove":
        slide = deck.get_slide(_normalize_slide_ref(args.get("slide")))
        deck.slides.remove(slide)
        return {
            "removed": slide.slide_id,
            "slide_count": len(deck.slides),
        }

    if command == "slide_set_layout":
        layout = get_layout(_require_string(args, "layout"))
        slide = deck.get_slide(_normalize_slide_ref(args.get("slide")))
        unbound_nodes = rebind_slots(deck, slide, layout)
        return {
            "slide_id": slide.slide_id,
            "layout": slide.layout,
            "unbound_nodes": unbound_nodes,
        }

    if command == "slot_set":
        slide = deck.get_slide(_normalize_slide_ref(args.get("slide")))
        slot_name = _resolve_slot_name(slide, _require_string(args, "slot"))
        content = _coerce_content(args)

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
        node.content = content

        if "font_size" in args:
            font_size = args["font_size"]
            if font_size is None:
                node.style_overrides.pop("font_size", None)
            elif isinstance(font_size, bool) or not isinstance(font_size, int | float):
                raise AgentSlidesError(SCHEMA_ERROR, "Argument 'font_size' must be a number")
            else:
                node.style_overrides["font_size"] = float(font_size)

        return {
            "slide_id": slide.slide_id,
            "slot": slot_name,
            "node_id": node.node_id,
            "text": node.content.to_plain_text(),
            "content": node.content.model_dump(mode="json"),
            "font_size": node.style_overrides.get("font_size"),
        }

    if command == "slot_clear":
        slide = deck.get_slide(_normalize_slide_ref(args.get("slide")))
        slot_name = _resolve_slot_name(slide, _require_string(args, "slot"))
        removed_ids = [node.node_id for node in _find_slot_nodes(slide, slot_name)]
        _prune_nodes(slide, set(removed_ids))
        return {
            "slide_id": slide.slide_id,
            "slot": slot_name,
            "removed_node_ids": removed_ids,
        }

    if command == "slot_bind":
        node_id = _require_string(args, "node")
        slide, node = _find_node(deck, node_id)
        slot_name = _resolve_slot_name(slide, _require_string(args, "slot"))
        conflicting_nodes = [
            candidate
            for candidate in _find_slot_nodes(slide, slot_name)
            if candidate.node_id != node.node_id
        ]
        _prune_nodes(slide, {candidate.node_id for candidate in conflicting_nodes})
        node.slot_binding = slot_name
        return {
            "slide_id": slide.slide_id,
            "slot": slot_name,
            "node_id": node.node_id,
        }

    raise AgentSlidesError(
        SCHEMA_ERROR,
        (
            f"Unsupported mutation command {command!r}. "
            f"Supported commands: {', '.join(sorted(SUPPORTED_MUTATION_COMMANDS))}"
        ),
    )
