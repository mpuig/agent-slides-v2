"""Reflow entry point.

The real layout engine lands in a later issue. For now the mutation pipeline
needs a stable call site that can be replaced without changing command code.
"""

from __future__ import annotations

from agent_slides.model import Deck, LayoutDef, Node, Slide


def rebind_slots(deck: Deck, slide: Slide, layout: LayoutDef) -> list[str]:
    """Retarget bound nodes onto a new layout and create missing slot nodes."""

    desired_slots = tuple(layout.slots)
    claimed_slots: set[str] = set()
    unbound_nodes: list[str] = []

    for node in slide.nodes:
        slot = node.slot_binding
        if slot is None:
            continue
        if slot in layout.slots and slot not in claimed_slots:
            claimed_slots.add(slot)
            continue
        node.slot_binding = None
        unbound_nodes.append(node.node_id)

    for slot_name in desired_slots:
        if slot_name in claimed_slots:
            continue
        slide.nodes.append(
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="text",
            )
        )

    slide.layout = layout.name
    return unbound_nodes


def reflow_deck(deck: Deck) -> None:
    """Stub reflow hook for the shared mutation pipeline."""

    _ = deck
