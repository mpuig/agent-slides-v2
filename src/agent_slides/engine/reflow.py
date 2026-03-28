"""Compute concrete slide geometry and resolved styling."""

from __future__ import annotations

from collections.abc import Iterable
from math import isclose

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.slide_revisions import resolve_slide_revision
from agent_slides.engine.text_fit import fit_text
from agent_slides.model import Deck, LayoutDef, Slide
from agent_slides.model.design_rules import DesignRules, load_design_rules
from agent_slides.model.layout_provider import BuiltinLayoutProvider, LayoutProvider
from agent_slides.model.layouts import (
    SLIDE_HEIGHT_PT,
    SLIDE_WIDTH_PT,
)
from agent_slides.model.themes import load_theme, resolve_style
from agent_slides.model.types import ComputedNode, Node, TextFitting, Theme


def _normalize_grid_indices(index: int | list[int]) -> list[int]:
    values = [index] if isinstance(index, int) else list(index)
    return sorted(value - 1 for value in values)


def _span_extent(
    *,
    proportions: Iterable[float],
    start_index: int,
    end_index: int,
    available_size: float,
    gutter: float,
) -> tuple[float, float]:
    values = list(proportions)
    offset = sum(values[:start_index]) * available_size + (start_index * gutter)
    span = sum(values[start_index : end_index + 1]) * available_size
    if end_index > start_index:
        span += (end_index - start_index) * gutter
    return offset, span


def _compute_slot_frame(layout_def: LayoutDef, slot_name: str, theme: Theme) -> tuple[float, float, float, float]:
    slot = layout_def.slots[slot_name]
    if None not in (slot.x, slot.y, slot.width, slot.height):
        return float(slot.x), float(slot.y), float(slot.width), float(slot.height)

    grid = layout_def.grid
    margin = 0.0 if slot.full_bleed else theme.spacing.margin
    gutter = 0.0 if slot.full_bleed else theme.spacing.gutter
    available_width = SLIDE_WIDTH_PT - (2 * margin)
    available_height = SLIDE_HEIGHT_PT - (2 * margin)

    rows = _normalize_grid_indices(slot.grid_row)
    row_start = rows[0]
    row_end = rows[-1]
    columns = _normalize_grid_indices(slot.grid_col)
    col_start = columns[0]
    col_end = columns[-1]

    x_offset, width = _span_extent(
        proportions=grid.col_widths,
        start_index=col_start,
        end_index=col_end,
        available_size=available_width,
        gutter=gutter,
    )
    y_offset, height = _span_extent(
        proportions=grid.row_heights,
        start_index=row_start,
        end_index=row_end,
        available_size=available_height,
        gutter=gutter,
    )
    return margin + x_offset, margin + y_offset, width, height


def _text_fit_rules(layout_def: LayoutDef, node: Node) -> TextFitting:
    slot_name = node.slot_binding or ""
    slot = layout_def.slots[slot_name]
    return layout_def.text_fitting[slot.role]


def _resolve_text_ladder(
    fit_rules: TextFitting,
    role: str,
    design_rules: DesignRules | None,
) -> list[float] | None:
    if fit_rules.ladder:
        return list(fit_rules.ladder)
    if design_rules is None:
        return None
    configured = design_rules.type_ladders.get(role, [])
    ladder = [size for size in configured if fit_rules.min_size <= size <= fit_rules.default_size]
    return ladder or None


def _normalize_deck_font_sizes(deck: Deck, provider: LayoutProvider, design_rules: DesignRules) -> None:
    if not design_rules.normalize_font_sizes:
        return

    role_minimums: dict[str, float] = {}
    entries: list[tuple[Node, ComputedNode, str, TextFitting, list[float] | None]] = []

    for slide in deck.slides:
        layout_def = provider.get_layout(slide.layout)
        for node in slide.nodes:
            if node.type != "text" or node.slot_binding is None:
                continue
            if node.node_id not in slide.computed:
                continue

            slot = layout_def.slots[node.slot_binding]
            if slot.role == "image":
                continue

            computed = slide.computed[node.node_id]
            fit_rules = provider.get_text_fitting(slide.layout, slot.role)
            ladder = _resolve_text_ladder(fit_rules, slot.role, design_rules)
            entries.append((node, computed, slot.role, fit_rules, ladder))
            current = role_minimums.get(slot.role)
            if current is None or computed.font_size_pt < current:
                role_minimums[slot.role] = computed.font_size_pt

    for node, computed, role, fit_rules, ladder in entries:
        target_size = role_minimums[role]
        if computed.font_size_pt <= target_size:
            continue
        if ladder is not None and not any(isclose(size, target_size, rel_tol=0.0, abs_tol=1e-6) for size in ladder):
            continue

        normalized_size, overflow = fit_text(
            text=node.content,
            width=computed.width,
            height=computed.height,
            default_size=fit_rules.default_size,
            min_size=fit_rules.min_size,
            role=role,
            font_family=computed.font_family,
            ladder=[target_size],
        )
        if overflow or not isclose(normalized_size, target_size, rel_tol=0.0, abs_tol=1e-6):
            continue
        computed.font_size_pt = normalized_size
        computed.text_overflow = False


def _reflow_slide(
    slide: Slide,
    layout_def: LayoutDef,
    theme: Theme,
    *,
    revision: int,
    design_rules: DesignRules | None = None,
) -> None:
    computed: dict[str, ComputedNode] = {}
    slide.revision = revision

    for node in slide.nodes:
        if node.slot_binding is None:
            continue
        if node.slot_binding not in layout_def.slots:
            raise AgentSlidesError(
                code=INVALID_SLOT,
                message=f"Slot '{node.slot_binding}' is not defined for layout '{layout_def.name}'.",
            )

        slot = layout_def.slots[node.slot_binding]
        x, y, width, height = _compute_slot_frame(layout_def, node.slot_binding, theme)
        if node.type == "chart":
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
        fit_rules = _text_fit_rules(layout_def, node)
        ladder = _resolve_text_ladder(fit_rules, slot.role, design_rules)
        font_size_pt, text_overflow = fit_text(
            text=node.content,
            width=width,
            height=height,
            default_size=fit_rules.default_size,
            min_size=fit_rules.min_size,
            role=slot.role,
            font_family=str(style["font_family"]),
            ladder=ladder,
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
    theme = getattr(active_provider, "theme", None) or load_theme(deck.theme)
    design_rules = load_design_rules(deck.design_rules)
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
            design_rules=design_rules,
        )
    _normalize_deck_font_sizes(deck, active_provider, design_rules)


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
