"""Compute concrete slide geometry and resolved styling."""

from __future__ import annotations

from collections.abc import Iterable

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.text_fit import fit_text
from agent_slides.model import Deck, LayoutDef, Slide, get_layout
from agent_slides.model.layouts import SLIDE_HEIGHT_PT, SLIDE_WIDTH_PT
from agent_slides.model.themes import load_theme, resolve_style
from agent_slides.model.types import ComputedNode, Node, TextFitting, Theme


def _normalize_columns(grid_col: int | list[int]) -> list[int]:
    columns = [grid_col] if isinstance(grid_col, int) else list(grid_col)
    return sorted(column - 1 for column in columns)


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


def _compute_slot_frame(layout_def: LayoutDef, slot_name: str) -> tuple[float, float, float, float]:
    slot = layout_def.slots[slot_name]
    grid = layout_def.grid
    margin = grid.margin
    gutter = grid.gutter
    available_width = SLIDE_WIDTH_PT - (2 * margin)
    available_height = SLIDE_HEIGHT_PT - (2 * margin)

    row_index = slot.grid_row - 1
    columns = _normalize_columns(slot.grid_col)
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
        start_index=row_index,
        end_index=row_index,
        available_size=available_height,
        gutter=gutter,
    )
    return margin + x_offset, margin + y_offset, width, height


def _text_fit_rules(layout_def: LayoutDef, node: Node) -> TextFitting:
    slot_name = node.slot_binding or ""
    slot = layout_def.slots[slot_name]
    return layout_def.text_fitting[slot.role]


def _reflow_slide(slide: Slide, layout_def: LayoutDef, theme: Theme, *, revision: int) -> None:
    computed: dict[str, ComputedNode] = {}

    for node in slide.nodes:
        if node.slot_binding is None:
            continue
        if node.slot_binding not in layout_def.slots:
            raise AgentSlidesError(
                code=INVALID_SLOT,
                message=f"Slot '{node.slot_binding}' is not defined for layout '{layout_def.name}'.",
            )

        slot = layout_def.slots[node.slot_binding]
        x, y, width, height = _compute_slot_frame(layout_def, node.slot_binding)
        fit_rules = _text_fit_rules(layout_def, node)
        font_size_pt, text_overflow = fit_text(
            text=node.content,
            width=width,
            height=height,
            default_size=fit_rules.default_size,
            min_size=fit_rules.min_size,
        )
        style = resolve_style(theme, slot.role)

        computed[node.node_id] = ComputedNode(
            x=x,
            y=y,
            width=width,
            height=height,
            font_size_pt=font_size_pt,
            font_family=str(style["font_family"]),
            color=str(style["color"]),
            bg_color=theme.colors.background,
            font_bold=bool(style["font_bold"]),
            text_overflow=text_overflow,
            revision=revision,
        )

    slide.computed = computed


def reflow_slide(slide: Slide, layout_def: LayoutDef, theme: Theme) -> None:
    """Compute concrete geometry and styling for a single slide."""

    _reflow_slide(slide, layout_def, theme, revision=0)


def reflow_deck(deck: Deck) -> None:
    """Reflow every slide in the deck using the deck theme."""

    theme = load_theme(deck.theme)
    for slide in deck.slides:
        _reflow_slide(slide, get_layout(slide.layout), theme, revision=deck.revision)


def rebind_slots(deck: Deck, slide: Slide, new_layout: LayoutDef) -> list[str]:
    """Keep compatible slot bindings and create missing nodes for a new layout."""

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
        slide.nodes.append(
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="text",
            )
        )

    slide.layout = new_layout.name
    return unbound_node_ids
