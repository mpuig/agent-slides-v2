"""Compute concrete slide geometry and resolved styling."""

from __future__ import annotations

from collections.abc import Callable

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.constraints import constraints_from_layout, solve
from agent_slides.engine.slide_revisions import resolve_slide_revision
from agent_slides.engine.text_fit import fit_text, measure_text_height
from agent_slides.model import Deck, LayoutDef, Slide
from agent_slides.model.layout_provider import BuiltinLayoutProvider, LayoutProvider
from agent_slides.model.layouts import (
    DEFAULT_TEXT_FITTING,
)
from agent_slides.model.themes import load_theme, resolve_style
from agent_slides.model.types import ComputedNode, Node, TextFitting, Theme


def _text_fit_rules(layout_def: LayoutDef, node: Node, provider: LayoutProvider | None = None) -> TextFitting:
    slot_name = node.slot_binding or ""
    slot = layout_def.slots[slot_name]
    if provider is not None:
        return provider.get_text_fitting(layout_def.name, slot.role)
    if slot.role in layout_def.text_fitting:
        return layout_def.text_fitting[slot.role]
    if slot.role == "heading":
        return DEFAULT_TEXT_FITTING["heading"]
    return DEFAULT_TEXT_FITTING["body"]


def _resolve_theme(deck: Deck, provider: LayoutProvider) -> Theme:
    return getattr(provider, "theme", None) or load_theme(deck.theme)


def _content_by_slot(slide: Slide) -> dict[str, Node]:
    return {
        node.slot_binding: node
        for node in slide.nodes
        if node.slot_binding is not None
    }


def _measure_slot_height_factory(layout_def: LayoutDef, provider: LayoutProvider) -> Callable[[str, object | None, float], float]:
    def measure(slot_name: str, content: object | None, width: float) -> float:
        node = content if isinstance(content, Node) else None
        if node is None:
            return 0.0
        fit_rules = _text_fit_rules(layout_def, node, provider)
        return measure_text_height(node.content, width, fit_rules.default_size)

    return measure


def _reflow_slide(
    slide: Slide,
    layout_def: LayoutDef,
    theme: Theme,
    *,
    revision: int,
    provider: LayoutProvider | None = None,
) -> None:
    computed: dict[str, ComputedNode] = {}
    slide.revision = revision
    slot_constraints = constraints_from_layout(layout_def, theme)
    content_by_slot = _content_by_slot(slide)
    measure = _measure_slot_height_factory(layout_def, provider or BuiltinLayoutProvider())
    rects = solve(slot_constraints, content_by_slot, measure)

    for node in slide.nodes:
        if node.slot_binding is None:
            continue
        if node.slot_binding not in layout_def.slots:
            raise AgentSlidesError(
                code=INVALID_SLOT,
                message=f"Slot '{node.slot_binding}' is not defined for layout '{layout_def.name}'.",
            )

        slot = layout_def.slots[node.slot_binding]
        rect = rects[node.slot_binding]
        x = rect.x
        y = rect.y
        width = rect.width
        height = rect.height
        if node.type == "chart":
            style = resolve_style(theme, slot.role)
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=0.0,
                font_family=str(style["font_family"]),
                color=str(style["color"]),
                bg_color=None,
                bg_transparency=0.0,
                font_bold=bool(style["font_bold"]),
                text_overflow=False,
                revision=revision,
                content_type="chart",
            )
            continue

        if slot.role == "image" or node.type == "image":
            image_fit = "stretch" if slot.full_bleed and node.image_fit == "contain" else node.image_fit
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=0.0,
                font_family=theme.fonts.body,
                color=theme.colors.text,
                bg_color=None,
                bg_transparency=0.0,
                font_bold=False,
                text_overflow=False,
                revision=revision,
                content_type="image",
                image_fit=image_fit,
            )
            continue

        style = resolve_style(theme, slot.role)
        fit_rules = _text_fit_rules(layout_def, node, provider)
        font_size_pt, text_overflow = fit_text(
            text=node.content,
            width=width,
            height=height,
            default_size=fit_rules.default_size,
            min_size=fit_rules.min_size,
        )

        computed[node.node_id] = ComputedNode(
            x=x,
            y=y,
            width=width,
            height=height,
            font_size_pt=font_size_pt,
            font_family=str(style["font_family"]),
            color=str(style["color"]),
            bg_color=slot.bg_color if slot.bg_color is not None else theme.colors.background,
            bg_transparency=slot.bg_transparency,
            font_bold=bool(style["font_bold"]),
            text_overflow=text_overflow,
            image_fit=node.image_fit,
            revision=revision,
            content_type="text",
        )

    slide.computed = computed


def reflow_slide(slide: Slide, layout_def: LayoutDef, theme: Theme) -> None:
    """Compute concrete geometry and styling for a single slide."""

    _reflow_slide(slide, layout_def, theme, revision=0)


def reflow_deck(
    deck: Deck,
    provider: LayoutProvider | None = None,
    *,
    previous_slide_signatures: dict[str, object] | None = None,
) -> None:
    """Reflow every slide in the deck using the deck theme."""

    active_provider = provider or BuiltinLayoutProvider()
    theme = _resolve_theme(deck, active_provider)
    for slide in deck.slides:
        layout_getter = active_provider.get_layout
        slide_revision = resolve_slide_revision(
            slide,
            deck_revision=deck.revision,
            previous_slide_signatures=previous_slide_signatures,
        )
        _reflow_slide(
            slide,
            layout_getter(slide.layout),
            theme,
            revision=slide_revision,
            provider=active_provider,
        )


def rebind_slots(
    deck: Deck,
    slide: Slide,
    new_layout: LayoutDef | str,
    provider: LayoutProvider | None = None,
) -> list[str]:
    """Keep compatible slot bindings and create missing nodes for a new layout."""

    if isinstance(new_layout, str):
        if provider is None:
            raise TypeError("provider is required when rebinding by layout name")
        layout_getter = provider.get_layout
        new_layout = layout_getter(new_layout)
    desired_slots = tuple(new_layout.slots)
    claimed_slots: set[str] = set()
    unbound_node_ids: list[str] = []

    for node in slide.nodes:
        slot_name = node.slot_binding
        if slot_name is None:
            continue
        if slot_name in new_layout.slots and slot_name not in claimed_slots:
            claimed_slots.add(slot_name)
            continue
        unbound_node_ids.append(node.node_id)
        node.slot_binding = None

    for slot_name in desired_slots:
        if slot_name in claimed_slots:
            continue
        slot = new_layout.slots[slot_name]
        slide.nodes.append(
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="image" if slot.role == "image" else "text",
                style_overrides={"placeholder": True} if slot.role == "image" else {},
            )
        )

    slide.layout = new_layout.name
    return unbound_node_ids
