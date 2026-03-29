"""Semantic render-oracle signals derived from deck and computed state."""

from __future__ import annotations

from typing import Any

from agent_slides.model import Deck, Node, SlotDef
from agent_slides.model.layout_provider import LayoutProvider

_MIN_SIGNAL_FONT_SIZE_PT = 8.0


def _node_has_semantic_content(node: Node) -> bool:
    if node.type == "text":
        return not node.content.is_empty()
    if node.type == "image":
        return bool(node.image_path and node.image_path.strip())
    if node.type == "chart":
        return node.chart_spec is not None
    if node.type == "table":
        return node.table_spec is not None
    if node.type == "icon":
        return bool(node.icon_name and node.icon_name.strip())
    if node.type == "pattern":
        return node.pattern_spec is not None
    return False


def _node_fills_slot(node: Node, slot: SlotDef) -> bool:
    if node.type not in slot.allowed_content:
        return False
    if slot.role == "image" and node.type != "image":
        return False
    return _node_has_semantic_content(node)


def generate_render_signals(deck: Deck, provider: LayoutProvider) -> list[dict[str, Any]]:
    """Return per-slide semantic signals for machine-consumable review."""

    payload: list[dict[str, Any]] = []
    for slide_index, slide in enumerate(deck.slides):
        layout = provider.get_layout(slide.layout)
        nodes_by_slot: dict[str, list[Node]] = {}
        for node in slide.nodes:
            if node.slot_binding is None:
                continue
            nodes_by_slot.setdefault(node.slot_binding, []).append(node)

        placeholder_empty = False
        image_missing = False
        for slot_name, slot in layout.slots.items():
            slot_nodes = nodes_by_slot.get(slot_name, [])
            if not any(_node_fills_slot(node, slot) for node in slot_nodes):
                placeholder_empty = True
            if slot.role == "image" and not any(
                node.type == "image" and bool(node.image_path and node.image_path.strip()) for node in slot_nodes
            ):
                image_missing = True

        text_clipped = any(
            computed.text_overflow
            for computed in slide.computed.values()
        )
        font_too_small = any(
            computed is not None and 0.0 < computed.font_size_pt < _MIN_SIGNAL_FONT_SIZE_PT
            for node in slide.nodes
            if node.type == "text"
            for computed in [slide.computed.get(node.node_id)]
        )

        payload.append(
            {
                "slide_index": slide_index,
                "layout_slug": slide.layout,
                "signals": {
                    "text_clipped": text_clipped,
                    "placeholder_empty": placeholder_empty,
                    "image_missing": image_missing,
                    "font_too_small": font_too_small,
                },
            }
        )

    return payload
