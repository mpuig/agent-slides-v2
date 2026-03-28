"""Text fitting heuristics for bounded text slots."""

from __future__ import annotations

from math import ceil

from agent_slides.model.types import NodeContent, TextBlock

AVG_CHAR_WIDTH_FACTOR = 0.6
LINE_HEIGHT_FACTOR = 1.2
SHRINK_STEP_PT = 2.0
BLOCK_SPACING_FACTOR = 0.3
HEADING_SIZE_FACTOR = 1.35
HEADING_LINE_HEIGHT_FACTOR = 1.1
BULLET_INDENT_PT = 18.0
BULLET_GLYPH_WIDTH_CHARS = 2.0


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


def _normalize_content(text: str | NodeContent) -> NodeContent:
    if isinstance(text, NodeContent):
        return text
    return NodeContent.from_text(text)


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


def measure_text_height(text: str | NodeContent, width: float, font_size: float) -> float:
    """Estimate the rendered height for text at a fixed font size."""

    content = _normalize_content(text)
    if width <= 0:
        return 0.0

    lines_height = 0.0
    blocks = content.blocks or [TextBlock(type="paragraph", text="")]
    for index, block in enumerate(blocks):
        block_font_size = font_size * _font_size_factor(block)
        block_width = _block_width(width, block, block_font_size)
        lines = _estimate_lines(block.text, block_width, block_font_size)
        lines_height += lines * block_font_size * _line_height_factor(block)
        if index < len(blocks) - 1:
            lines_height += font_size * BLOCK_SPACING_FACTOR
    return lines_height


def _fits(content: NodeContent, width: float, height: float, font_size: float) -> bool:
    return measure_text_height(content, width, font_size) <= height
