"""Text fitting heuristics for bounded text slots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil

from agent_slides.model.design_rules import BlockSpacingRules
from agent_slides.model.types import BlockPosition, NodeContent, SlotVerticalAlign, TextBlock, TextFitting

AVG_CHAR_WIDTH_FACTOR = 0.6
LINE_HEIGHT_FACTOR = 1.2
SHRINK_STEP_PT = 2.0
BLOCK_SPACING_FACTOR = 0.3
HEADING_SIZE_FACTOR = 1.35
HEADING_LINE_HEIGHT_FACTOR = 1.1
BULLET_INDENT_PT = 18.0
BULLET_GLYPH_WIDTH_CHARS = 2.0


@dataclass(frozen=True)
class BlockFit:
    block_index: int
    block: TextBlock
    role: str
    font_size_pt: float
    rendered_height: float
    line_count: int


@dataclass
class _BlockFitState:
    block_index: int
    block: TextBlock
    role: str
    ladder: list[float]
    ladder_index: int = 0
    rendered_height: float = 0.0
    line_count: int = 1

    @property
    def font_size_pt(self) -> float:
        return self.ladder[self.ladder_index]


def fit_text(
    text: str | NodeContent,
    width: float,
    height: float,
    default_size: float,
    min_size: float = 10.0,
) -> tuple[float, bool]:
    """Estimate a font size that fits text into a bounded area."""
    content = _normalize_content(text)

    if width <= 0 or height <= 0:
        return min_size, True

    if content.is_empty():
        return default_size, False

    if len(content.to_plain_text()) == 1:
        return default_size, False

    font_size = default_size

    while font_size > min_size:
        if _fits(content, width, height, font_size):
            return font_size, False

        font_size -= SHRINK_STEP_PT

    if _fits(content, width, height, min_size):
        return min_size, False

    return min_size, True


def fit_blocks(
    blocks: list[TextBlock],
    width: float,
    height: float,
    *,
    role: str,
    text_fitting: Mapping[str, TextFitting],
    spacing_rules: BlockSpacingRules,
) -> tuple[list[BlockFit], bool]:
    """Fit structured blocks independently, then shrink to the slot height if needed."""

    normalized_blocks = blocks or [TextBlock(type="paragraph", text="")]
    width_overflow = width <= 0
    height_overflow = height <= 0
    available_width = max(width, 1.0)
    available_height = max(height, 0.0)

    states: list[_BlockFitState] = []
    for block_index, block in enumerate(normalized_blocks):
        block_role = "heading" if block.type == "heading" else role
        ladder = _font_ladder(_text_fitting_for_role(text_fitting, block_role))
        state = _BlockFitState(
            block_index=block_index,
            block=block,
            role=block_role,
            ladder=ladder,
        )
        _refresh_block_fit(state, available_width)
        states.append(state)

    _shrink_states_to_fit(states, available_width, available_height, spacing_rules)

    fits = [
        BlockFit(
            block_index=state.block_index,
            block=state.block,
            role=state.role,
            font_size_pt=state.font_size_pt,
            rendered_height=state.rendered_height,
            line_count=state.line_count,
        )
        for state in states
    ]
    overflowed = width_overflow or height_overflow or total_height(fits, spacing_rules=spacing_rules) > available_height
    return fits, overflowed


def compose_blocks(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    padding: float,
    vertical_align: SlotVerticalAlign,
    block_fits: list[BlockFit],
    spacing_rules: BlockSpacingRules,
) -> list[BlockPosition]:
    """Resolve fitted blocks into concrete positions inside a slot."""

    content_x = x + padding
    content_y = y + padding
    content_width = max(width - (2 * padding), 0.0)
    available_height = max(height - (2 * padding), 0.0)
    content_height = total_height(block_fits, spacing_rules=spacing_rules)
    remaining_height = max(available_height - content_height, 0.0)

    if vertical_align == "middle":
        start_y = content_y + (remaining_height / 2)
    elif vertical_align == "bottom":
        start_y = content_y + remaining_height
    else:
        start_y = content_y

    positions: list[BlockPosition] = []
    cursor_y = start_y
    for index, fit in enumerate(block_fits):
        positions.append(
            BlockPosition(
                block_index=fit.block_index,
                x=content_x,
                y=cursor_y,
                width=content_width,
                height=fit.rendered_height,
                font_size_pt=fit.font_size_pt,
            )
        )
        if index < len(block_fits) - 1:
            cursor_y += fit.rendered_height + spacing_between(fit.block, block_fits[index + 1].block, spacing_rules)

    return positions


def spacing_between(previous: TextBlock, current: TextBlock, spacing_rules: BlockSpacingRules) -> float:
    return spacing_rules.between(previous.type, current.type)


def total_height(block_fits: list[BlockFit], *, spacing_rules: BlockSpacingRules) -> float:
    if not block_fits:
        return 0.0

    spacing_total = 0.0
    for index in range(len(block_fits) - 1):
        spacing_total += spacing_between(block_fits[index].block, block_fits[index + 1].block, spacing_rules)
    return sum(fit.rendered_height for fit in block_fits) + spacing_total


def _normalize_content(text: str | NodeContent) -> NodeContent:
    if isinstance(text, NodeContent):
        return text
    return NodeContent.from_text(text)


def _text_fitting_for_role(text_fitting: Mapping[str, TextFitting], role: str) -> TextFitting:
    rules = text_fitting.get(role)
    if rules is not None:
        return rules

    fallback = text_fitting.get("body") or text_fitting.get("heading")
    if fallback is not None:
        return fallback

    return TextFitting(default_size=18.0, min_size=10.0)


def _font_ladder(fitting: TextFitting) -> list[float]:
    sizes: list[float] = []
    size = float(fitting.default_size)
    minimum = float(fitting.min_size)

    while size > minimum:
        sizes.append(size)
        size -= SHRINK_STEP_PT

    if not sizes or sizes[-1] != minimum:
        sizes.append(minimum)

    return sizes


def _font_size_factor(block: TextBlock) -> float:
    if block.type == "heading":
        return HEADING_SIZE_FACTOR
    return 1.0


def _line_height_factor(block: TextBlock) -> float:
    if block.type == "heading":
        return HEADING_LINE_HEIGHT_FACTOR
    return LINE_HEIGHT_FACTOR


def _block_width(width: float, block: TextBlock, font_size: float) -> float:
    available_width = width
    if block.type == "bullet":
        available_width -= block.level * BULLET_INDENT_PT
        available_width -= BULLET_GLYPH_WIDTH_CHARS * AVG_CHAR_WIDTH_FACTOR * font_size
    return max(available_width, 1.0)


def _estimate_lines(text: str, width: float, font_size: float) -> int:
    avg_char_width = AVG_CHAR_WIDTH_FACTOR * font_size

    if avg_char_width <= 0:
        return max(len(text), 1)

    chars_per_line = width / avg_char_width

    # Treat sub-character widths as one character per line to avoid division blowups.
    if chars_per_line < 1:
        return max(len(text), 1)

    return max(sum(ceil(len(line) / chars_per_line) or 1 for line in text.splitlines()), 1)


def _fits(content: NodeContent, width: float, height: float, font_size: float) -> bool:
    lines_height = 0.0
    blocks = content.blocks or [TextBlock(type="paragraph", text="")]
    for index, block in enumerate(blocks):
        block_font_size = font_size * _font_size_factor(block)
        block_width = _block_width(width, block, block_font_size)
        lines = _estimate_lines(block.text, block_width, block_font_size)
        lines_height += lines * block_font_size * _line_height_factor(block)
        if index < len(blocks) - 1:
            lines_height += font_size * BLOCK_SPACING_FACTOR

    return lines_height <= height


def _refresh_block_fit(state: _BlockFitState, width: float) -> None:
    font_size = state.font_size_pt
    block_width = _block_width(width, state.block, font_size)
    line_count = _estimate_lines(state.block.text, block_width, font_size)
    state.line_count = line_count
    state.rendered_height = line_count * font_size * _line_height_factor(state.block)


def _shrink_states_to_fit(
    states: list[_BlockFitState],
    width: float,
    height: float,
    spacing_rules: BlockSpacingRules,
) -> None:
    for shrink_heading in (False, True):
        while _states_total_height(states, spacing_rules) > height:
            candidates = [
                state
                for state in states
                if (state.block.type == "heading") is shrink_heading and state.ladder_index < len(state.ladder) - 1
            ]
            if not candidates:
                return

            candidate = max(candidates, key=lambda state: (state.font_size_pt, -state.block_index))
            candidate.ladder_index += 1
            _refresh_block_fit(candidate, width)


def _states_total_height(states: list[_BlockFitState], spacing_rules: BlockSpacingRules) -> float:
    fits = [
        BlockFit(
            block_index=state.block_index,
            block=state.block,
            role=state.role,
            font_size_pt=state.font_size_pt,
            rendered_height=state.rendered_height,
            line_count=state.line_count,
        )
        for state in states
    ]
    return total_height(fits, spacing_rules=spacing_rules)
