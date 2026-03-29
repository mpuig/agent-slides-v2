"""Post-solve structural validation for layout geometry."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Literal, Mapping

from agent_slides.engine.constraints import Rect
from agent_slides.model.layouts import SLIDE_HEIGHT_PT, SLIDE_WIDTH_PT
from agent_slides.model.types import ComputedNode, LayoutDef

PEER_TOP_MISMATCH = "PEER_TOP_MISMATCH"
PEER_WIDTH_MISMATCH = "PEER_WIDTH_MISMATCH"
GUTTER_MISMATCH = "GUTTER_MISMATCH"
SAFE_MARGIN_VIOLATION = "SAFE_MARGIN_VIOLATION"
SLOT_OVERLAP = "SLOT_OVERLAP"
TEXT_OVERFLOW = "TEXT_OVERFLOW"


@dataclass(frozen=True)
class LayoutViolation:
    code: str
    severity: Literal["error", "warning"]
    message: str
    slot_refs: tuple[str, ...]


def _slot_groups(layout: LayoutDef, attribute: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for slot_name, slot in layout.slots.items():
        group_name = getattr(slot, attribute)
        if group_name:
            groups[str(group_name)].append(slot_name)
    return groups


def _add_violation(
    violations: list[LayoutViolation],
    *,
    code: str,
    message: str,
    slot_refs: list[str] | tuple[str, ...],
    severity: Literal["error", "warning"] = "error",
) -> None:
    violations.append(
        LayoutViolation(
            code=code,
            severity=severity,
            message=message,
            slot_refs=tuple(dict.fromkeys(slot_refs)),
        )
    )


def _validate_peer_tops(
    layout: LayoutDef,
    rects: Mapping[str, Rect],
    epsilon: float,
    violations: list[LayoutViolation],
) -> None:
    for group_name, slot_names in _slot_groups(layout, "alignment_group").items():
        if len(slot_names) < 2:
            continue
        ordered = sorted(
            slot_names,
            key=lambda slot_name: (rects[slot_name].y, rects[slot_name].x, slot_name),
        )
        anchor_slot = ordered[0]
        anchor_top = rects[anchor_slot].y
        for slot_name in ordered[1:]:
            top = rects[slot_name].y
            if abs(top - anchor_top) <= epsilon:
                continue
            _add_violation(
                violations,
                code=PEER_TOP_MISMATCH,
                message=(
                    f"Alignment group '{group_name}' must share a common top edge within {epsilon:g}pt; "
                    f"'{anchor_slot}' is at {anchor_top:g}pt and '{slot_name}' is at {top:g}pt."
                ),
                slot_refs=[anchor_slot, slot_name],
            )


def _validate_peer_widths(
    layout: LayoutDef,
    rects: Mapping[str, Rect],
    epsilon: float,
    violations: list[LayoutViolation],
) -> None:
    for group_name, slot_names in _slot_groups(layout, "peer_group").items():
        if len(slot_names) < 2:
            continue
        ordered = sorted(
            slot_names,
            key=lambda slot_name: (
                rects[slot_name].width,
                rects[slot_name].x,
                slot_name,
            ),
        )
        anchor_slot = ordered[0]
        anchor_width = rects[anchor_slot].width
        for slot_name in ordered[1:]:
            width = rects[slot_name].width
            if abs(width - anchor_width) <= epsilon:
                continue
            _add_violation(
                violations,
                code=PEER_WIDTH_MISMATCH,
                message=(
                    f"Peer group '{group_name}' requires equal widths within {epsilon:g}pt; "
                    f"'{anchor_slot}' is {anchor_width:g}pt wide and '{slot_name}' is {width:g}pt wide."
                ),
                slot_refs=[anchor_slot, slot_name],
            )


def _validate_gutters(
    layout: LayoutDef,
    rects: Mapping[str, Rect],
    epsilon: float,
    violations: list[LayoutViolation],
) -> None:
    for group_name, slot_names in _slot_groups(layout, "peer_group").items():
        if len(slot_names) < 3:
            continue
        ordered = sorted(
            slot_names,
            key=lambda slot_name: (rects[slot_name].x, rects[slot_name].y, slot_name),
        )
        gutters: list[tuple[str, str, float]] = []
        for left_slot, right_slot in zip(ordered, ordered[1:], strict=False):
            left_rect = rects[left_slot]
            right_rect = rects[right_slot]
            gutters.append(
                (left_slot, right_slot, right_rect.x - (left_rect.x + left_rect.width))
            )
        anchor_left, anchor_right, anchor_gutter = gutters[0]
        for left_slot, right_slot, gutter in gutters[1:]:
            if abs(gutter - anchor_gutter) <= epsilon:
                continue
            _add_violation(
                violations,
                code=GUTTER_MISMATCH,
                message=(
                    f"Peer group '{group_name}' requires consistent gutters within {epsilon:g}pt; "
                    f"'{anchor_left}'→'{anchor_right}' is {anchor_gutter:g}pt but "
                    f"'{left_slot}'→'{right_slot}' is {gutter:g}pt."
                ),
                slot_refs=[anchor_left, anchor_right, left_slot, right_slot],
            )


def _validate_bounds(
    rects: Mapping[str, Rect],
    *,
    slide_width: float,
    slide_height: float,
    epsilon: float,
    violations: list[LayoutViolation],
) -> None:
    for slot_name, rect in rects.items():
        right = rect.x + rect.width
        bottom = rect.y + rect.height
        if (
            rect.x >= -epsilon
            and rect.y >= -epsilon
            and right <= slide_width + epsilon
            and bottom <= slide_height + epsilon
        ):
            continue
        _add_violation(
            violations,
            code=SAFE_MARGIN_VIOLATION,
            message=(
                f"Slot '{slot_name}' must remain inside the slide bounds; "
                f"got x={rect.x:g}, y={rect.y:g}, width={rect.width:g}, height={rect.height:g} "
                f"for a {slide_width:g}x{slide_height:g}pt slide."
            ),
            slot_refs=[slot_name],
        )


def _validate_overlap(
    rects: Mapping[str, Rect],
    epsilon: float,
    violations: list[LayoutViolation],
) -> None:
    for left_slot, right_slot in combinations(sorted(rects), 2):
        left_rect = rects[left_slot]
        right_rect = rects[right_slot]
        overlap_width = min(
            left_rect.x + left_rect.width, right_rect.x + right_rect.width
        ) - max(left_rect.x, right_rect.x)
        overlap_height = min(
            left_rect.y + left_rect.height, right_rect.y + right_rect.height
        ) - max(left_rect.y, right_rect.y)
        if overlap_width <= epsilon or overlap_height <= epsilon:
            continue
        _add_violation(
            violations,
            code=SLOT_OVERLAP,
            message=(
                f"Slots '{left_slot}' and '{right_slot}' overlap by "
                f"{overlap_width:g}x{overlap_height:g}pt."
            ),
            slot_refs=[left_slot, right_slot],
        )


def _validate_overflow(
    computed_by_slot: Mapping[str, ComputedNode],
    violations: list[LayoutViolation],
) -> None:
    for slot_name, computed in computed_by_slot.items():
        if computed.content_type != "text" or not computed.text_overflow:
            continue
        _add_violation(
            violations,
            code=TEXT_OVERFLOW,
            message=f"Slot '{slot_name}' reports explicit text overflow after fitting.",
            slot_refs=[slot_name],
        )


def validate_layout(
    layout: LayoutDef,
    rects: Mapping[str, Rect],
    epsilon: float = 1.0,
    *,
    computed_by_slot: Mapping[str, ComputedNode] | None = None,
    slide_width: float = SLIDE_WIDTH_PT,
    slide_height: float = SLIDE_HEIGHT_PT,
) -> list[LayoutViolation]:
    """Validate solved slot geometry against layout invariants."""

    violations: list[LayoutViolation] = []
    _validate_peer_tops(layout, rects, epsilon, violations)
    _validate_peer_widths(layout, rects, epsilon, violations)
    _validate_gutters(layout, rects, epsilon, violations)
    _validate_bounds(
        rects,
        slide_width=slide_width,
        slide_height=slide_height,
        epsilon=epsilon,
        violations=violations,
    )
    _validate_overlap(rects, epsilon, violations)
    if computed_by_slot is not None:
        _validate_overflow(computed_by_slot, violations)
    return violations
