"""Constraint generation and solving for slide layout reflow."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.model.layouts import SLIDE_HEIGHT_PT, SLIDE_WIDTH_PT
from agent_slides.model.types import LayoutDef, Theme


@dataclass(frozen=True)
class Anchor:
    reference: str
    edge: str
    offset: float = 0.0


@dataclass(frozen=True)
class SlotConstraints:
    left: Anchor
    top: Anchor
    right: Anchor
    bottom: Anchor | None = None
    height_mode: str = "fixed"
    width_mode: str = "fixed"
    reading_order: int = 0
    share_group: str | None = None


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


MeasureFn = Callable[[str, object | None, float], float]


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


def _compute_slot_frame(layout_def: LayoutDef, slot_name: str, theme: Theme) -> Rect:
    slot = layout_def.slots[slot_name]
    if None not in (slot.x, slot.y, slot.width, slot.height):
        return Rect(float(slot.x), float(slot.y), float(slot.width), float(slot.height))

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
    return Rect(margin + x_offset, margin + y_offset, width, height)


def _slide_edge_offset(value: float, edge: str, axis_size: float) -> Anchor:
    if edge in {"left", "top"}:
        return Anchor(reference="slide", edge=edge, offset=value)
    return Anchor(reference="slide", edge=edge, offset=value - axis_size)


def _slot_row_key(layout_def: LayoutDef, slot_name: str) -> tuple[int, ...]:
    slot = layout_def.slots[slot_name]
    return tuple(_normalize_grid_indices(slot.grid_row))


def _is_template_bounds_layout(layout_def: LayoutDef) -> bool:
    grid = layout_def.grid
    return (
        grid.columns == 1
        and grid.rows == 1
        and grid.col_widths == [1.0]
        and grid.row_heights == [1.0]
        and grid.margin == 0.0
        and grid.gutter == 0.0
    )


def constraints_from_layout(layout_def: LayoutDef, theme: Theme) -> dict[str, SlotConstraints]:
    """Convert a layout definition into solver-friendly slot constraints."""

    constraints: dict[str, SlotConstraints] = {}
    shared_vertical_bounds: dict[str, tuple[Anchor, Anchor]] = {}
    share_groups: dict[str, list[str]] = defaultdict(list)
    preserve_explicit_bounds = _is_template_bounds_layout(layout_def)

    for index, slot_name in enumerate(layout_def.slots):
        slot = layout_def.slots[slot_name]
        frame = _compute_slot_frame(layout_def, slot_name, theme)
        left = _slide_edge_offset(frame.x, "left", SLIDE_WIDTH_PT)
        right = _slide_edge_offset(frame.x + frame.width, "right", SLIDE_WIDTH_PT)

        group = None if preserve_explicit_bounds else slot.alignment_group
        if group and group in shared_vertical_bounds:
            top, bottom = shared_vertical_bounds[group]
        else:
            top = _slide_edge_offset(frame.y, "top", SLIDE_HEIGHT_PT)
            bottom = _slide_edge_offset(frame.y + frame.height, "bottom", SLIDE_HEIGHT_PT)
            if group:
                shared_vertical_bounds[group] = (top, bottom)

        share_group = None
        if slot.width_mode == "equal_share":
            share_group = slot.alignment_group or f"{layout_def.name}:row:{_slot_row_key(layout_def, slot_name)!r}"
            share_groups[share_group].append(slot_name)

        constraints[slot_name] = SlotConstraints(
            left=left,
            top=top,
            right=right,
            bottom=None if slot.height_mode != "fixed" else bottom,
            height_mode=slot.height_mode,
            width_mode=slot.width_mode,
            reading_order=slot.reading_order if slot.reading_order is not None else index,
            share_group=share_group,
        )

    validate_constraints(constraints)
    return constraints


def _constraint_dependencies(slot_name: str, constraint: SlotConstraints, known_slots: set[str]) -> set[str]:
    dependencies: set[str] = set()
    for anchor in (constraint.left, constraint.top, constraint.right, constraint.bottom):
        if anchor is None or anchor.reference == "slide":
            continue
        if anchor.reference not in known_slots:
            raise AgentSlidesError(
                INVALID_SLOT,
                f"Constraint for slot '{slot_name}' references unknown slot '{anchor.reference}'.",
            )
        dependencies.add(anchor.reference)
    return dependencies


def _ordered_constraints(constraints: Mapping[str, SlotConstraints]) -> list[str]:
    known_slots = set(constraints)
    dependencies = {
        slot_name: _constraint_dependencies(slot_name, constraint, known_slots)
        for slot_name, constraint in constraints.items()
    }
    dependents: dict[str, set[str]] = {slot_name: set() for slot_name in constraints}
    indegree = {slot_name: len(slot_dependencies) for slot_name, slot_dependencies in dependencies.items()}
    for slot_name, slot_dependencies in dependencies.items():
        for dependency in slot_dependencies:
            dependents[dependency].add(slot_name)

    order: list[str] = []
    ready = sorted(
        (slot_name for slot_name, degree in indegree.items() if degree == 0),
        key=lambda slot_name: (constraints[slot_name].reading_order, slot_name),
    )
    while ready:
        slot_name = ready.pop(0)
        order.append(slot_name)
        for dependent in sorted(
            dependents[slot_name],
            key=lambda name: (constraints[name].reading_order, name),
        ):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort(key=lambda name: (constraints[name].reading_order, name))

    if len(order) == len(constraints):
        return order

    unresolved = [slot_name for slot_name in constraints if slot_name not in order]
    cycle = " -> ".join(sorted(unresolved))
    raise AgentSlidesError(INVALID_SLOT, f"Constraint graph contains a cycle: {cycle}")


def validate_constraints(constraints: Mapping[str, SlotConstraints]) -> None:
    """Raise when the constraint graph is invalid or cyclic."""

    _ordered_constraints(constraints)


def _resolve_anchor(anchor: Anchor, resolved: Mapping[str, Rect], slide_width: float, slide_height: float) -> float:
    if anchor.reference == "slide":
        if anchor.edge == "left":
            return anchor.offset
        if anchor.edge == "right":
            return slide_width + anchor.offset
        if anchor.edge == "top":
            return anchor.offset
        if anchor.edge == "bottom":
            return slide_height + anchor.offset
        if anchor.edge == "center_x":
            return (slide_width / 2.0) + anchor.offset
        raise AgentSlidesError(INVALID_SLOT, f"Unsupported slide anchor edge '{anchor.edge}'.")

    rect = resolved[anchor.reference]
    if anchor.edge == "left":
        return rect.x + anchor.offset
    if anchor.edge == "right":
        return rect.x + rect.width + anchor.offset
    if anchor.edge == "top":
        return rect.y + anchor.offset
    if anchor.edge == "bottom":
        return rect.y + rect.height + anchor.offset
    if anchor.edge == "center_x":
        return rect.x + (rect.width / 2.0) + anchor.offset
    raise AgentSlidesError(INVALID_SLOT, f"Unsupported slot anchor edge '{anchor.edge}'.")


def solve(
    constraints: Mapping[str, SlotConstraints],
    content: Mapping[str, object] | None,
    measurer: MeasureFn,
    slide_width: float = SLIDE_WIDTH_PT,
    slide_height: float = SLIDE_HEIGHT_PT,
) -> dict[str, Rect]:
    """Resolve slot rectangles from constraints in dependency order."""

    order = _ordered_constraints(constraints)
    resolved: dict[str, Rect] = {}
    content = content or {}

    share_groups: dict[str, list[str]] = defaultdict(list)
    for slot_name in constraints:
        group = constraints[slot_name].share_group
        if group:
            share_groups[group].append(slot_name)
    for group_name, members in share_groups.items():
        members.sort(key=lambda slot_name: (constraints[slot_name].reading_order, slot_name))
        share_groups[group_name] = members

    for slot_name in order:
        constraint = constraints[slot_name]
        left = _resolve_anchor(constraint.left, resolved, slide_width, slide_height)
        right = _resolve_anchor(constraint.right, resolved, slide_width, slide_height)

        if constraint.width_mode == "equal_share" and constraint.share_group is not None:
            members = share_groups[constraint.share_group]
            share_width = (right - left) / max(len(members), 1)
            member_index = members.index(slot_name)
            left = left + (share_width * member_index)
            right = left + share_width

        top = _resolve_anchor(constraint.top, resolved, slide_width, slide_height)
        width = right - left

        if constraint.height_mode == "fit_content":
            height = float(measurer(slot_name, content.get(slot_name), width))
        else:
            bottom = (
                _resolve_anchor(constraint.bottom, resolved, slide_width, slide_height)
                if constraint.bottom is not None
                else slide_height
            )
            height = bottom - top

        resolved[slot_name] = Rect(x=left, y=top, width=width, height=height)

    return resolved
