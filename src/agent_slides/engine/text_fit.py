"""Text fitting heuristics for bounded text slots."""

from __future__ import annotations

from math import ceil

from PIL import ImageFont

from agent_slides.model.types import NodeContent, TextBlock

TYPE_LADDERS = {
    "heading": [36.0, 32.0, 28.0, 24.0],
    "body": [18.0, 16.0, 14.0, 12.0, 10.0],
    "quote": [28.0, 24.0, 20.0, 18.0],
    "attribution": [16.0, 14.0, 12.0, 10.0],
}
FONT_WIDTH_FACTORS = {
    "calibri": 0.52,
    "arial": 0.55,
    "georgia": 0.56,
    "times new roman": 0.50,
    "helvetica": 0.54,
}
DEFAULT_WIDTH_FACTOR = 0.55
ROLE_STEP_PT = {
    "heading": 4.0,
    "body": 2.0,
    "quote": 4.0,
    "attribution": 2.0,
}
LINE_HEIGHT_FACTOR = 1.2
BLOCK_SPACING_FACTOR = 0.3
HEADING_SIZE_FACTOR = 1.35
HEADING_LINE_HEIGHT_FACTOR = 1.1
BULLET_INDENT_PT = 18.0
BULLET_GLYPH_WIDTH_CHARS = 2.0


def fit_text(
    text: str | NodeContent,
    width: float,
    height: float,
    default_size: float | None = None,
    min_size: float = 10.0,
    role: str = "body",
    *,
    font_family: str | None = None,
    ladder: list[float] | None = None,
    use_precise: bool = False,
) -> tuple[float, bool]:
    """Estimate a font size that fits text into a bounded area."""

    content = _normalize_content(text)
    sizes = _resolve_ladder(role, default_size=default_size, min_size=min_size, ladder=ladder)
    largest_size = sizes[0]
    smallest_size = sizes[-1]

    if width <= 0 or height <= 0:
        return smallest_size, True

    if content.is_empty():
        return largest_size, False

    if len(content.to_plain_text()) == 1:
        return largest_size, False

    for font_size in sizes:
        if _fits(content, width, height, font_size, font_family=font_family, use_precise=use_precise):
            return font_size, False

    return smallest_size, True


def measure_text_height(
    text: str | NodeContent,
    width: float,
    font_size: float,
    *,
    font_family: str | None = None,
    use_precise: bool = False,
) -> float:
    """Estimate rendered text height at a fixed font size."""

    if width <= 0:
        return 0.0
    return _measured_text_height(
        _normalize_content(text),
        width,
        font_size,
        font_family=font_family,
        use_precise=use_precise,
    )


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


def _normalize_font_family(font_family: str | None) -> str:
    if not font_family:
        return ""
    return font_family.strip().casefold()


def _width_factor(font_family: str | None) -> float:
    return FONT_WIDTH_FACTORS.get(_normalize_font_family(font_family), DEFAULT_WIDTH_FACTOR)


def _sanitize_ladder(values: list[float]) -> list[float]:
    seen: set[float] = set()
    sanitized: list[float] = []
    for value in values:
        size = float(value)
        if size <= 0:
            continue
        if size in seen:
            continue
        seen.add(size)
        sanitized.append(size)
    return sorted(sanitized, reverse=True)


def _role_step(role: str) -> float:
    return ROLE_STEP_PT.get(role, 2.0)


def _build_role_ladder(role: str, *, default_size: float, min_size: float) -> list[float]:
    step = _role_step(role)
    size = float(default_size)
    ladder = [size]
    while size - step > min_size:
        size -= step
        ladder.append(size)
    if ladder[-1] != float(min_size):
        ladder.append(float(min_size))
    return _sanitize_ladder(ladder)


def _resolve_ladder(
    role: str,
    *,
    default_size: float | None,
    min_size: float,
    ladder: list[float] | None,
) -> list[float]:
    if ladder is not None:
        sanitized = _sanitize_ladder(ladder)
        if sanitized:
            return sanitized

    if default_size is not None:
        return _build_role_ladder(role, default_size=default_size, min_size=min_size)

    configured = TYPE_LADDERS.get(role)
    if configured:
        return list(configured)

    return [float(min_size)]


def _block_width(width: float, block: TextBlock, font_size: float, *, font_family: str | None) -> float:
    available_width = width
    if block.type == "bullet":
        available_width -= block.level * BULLET_INDENT_PT
        available_width -= BULLET_GLYPH_WIDTH_CHARS * _width_factor(font_family) * font_size
    return max(available_width, 1.0)


def _estimate_lines(text: str, width: float, font_size: float, *, font_family: str | None) -> int:
    avg_char_width = _width_factor(font_family) * font_size

    if avg_char_width <= 0:
        return max(len(text), 1)

    chars_per_line = width / avg_char_width

    if chars_per_line < 1:
        return max(len(text), 1)

    return max(sum(ceil(len(line) / chars_per_line) or 1 for line in text.splitlines()), 1)


def _fallback_font_name(font_family: str | None) -> str:
    lowered = _normalize_font_family(font_family)
    if lowered in {"georgia", "times new roman"}:
        return "DejaVuSerif.ttf"
    return "DejaVuSans.ttf"


def _load_precise_font(font_family: str | None, size: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    requested_size = max(int(round(size)), 1)
    candidates: list[str] = []
    if font_family and font_family.strip():
        candidates.append(font_family.strip())
    candidates.append(_fallback_font_name(font_family))

    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, requested_size)
        except OSError:
            continue

    return ImageFont.load_default()


def _measure_precise_width(text: str, font: ImageFont.ImageFont) -> float:
    if text == "":
        return 0.0
    return float(font.getlength(text))


def _measure_precise_line_height(font: ImageFont.ImageFont) -> float:
    left, top, right, bottom = font.getbbox("Ag")
    height = float(bottom - top)
    if height > 0:
        return height
    return float(getattr(font, "size", 0) or 1.0)


def _wrap_precise_line(text: str, width: float, font: ImageFont.ImageFont) -> list[str]:
    if text == "":
        return [""]

    lines: list[str] = []
    remaining = text
    while remaining:
        if _measure_precise_width(remaining, font) <= width:
            lines.append(remaining)
            break

        last_fit = 0
        last_whitespace = 0
        for index in range(1, len(remaining) + 1):
            chunk = remaining[:index]
            if _measure_precise_width(chunk, font) > width:
                break
            last_fit = index
            if chunk[-1].isspace():
                last_whitespace = index

        split_at = last_whitespace or last_fit or 1
        line = remaining[:split_at].rstrip() or remaining[:split_at]
        lines.append(line)
        remaining = remaining[split_at:].lstrip()

    return lines or [""]


def _estimate_lines_precise(text: str, width: float, font: ImageFont.ImageFont) -> tuple[int, float]:
    paragraphs = text.splitlines() or [""]
    lines = 0
    max_height = 0.0
    for paragraph in paragraphs:
        wrapped = _wrap_precise_line(paragraph, width, font)
        lines += len(wrapped)
        max_height = max(max_height, _measure_precise_line_height(font))
    return max(lines, 1), max(max_height, 1.0)


def _measured_text_height(
    content: NodeContent,
    width: float,
    font_size: float,
    *,
    font_family: str | None,
    use_precise: bool,
) -> float:
    lines_height = 0.0
    blocks = content.blocks or [TextBlock(type="paragraph", text="")]
    for index, block in enumerate(blocks):
        block_font_size = font_size * _font_size_factor(block)
        block_width = _block_width(width, block, block_font_size, font_family=font_family)
        if use_precise:
            font = _load_precise_font(font_family, block_font_size)
            lines, line_height = _estimate_lines_precise(block.text, block_width, font)
        else:
            lines = _estimate_lines(block.text, block_width, block_font_size, font_family=font_family)
            line_height = block_font_size

        lines_height += lines * line_height * _line_height_factor(block)
        if index < len(blocks) - 1:
            lines_height += font_size * BLOCK_SPACING_FACTOR

    return lines_height


def _fits(
    content: NodeContent,
    width: float,
    height: float,
    font_size: float,
    *,
    font_family: str | None,
    use_precise: bool,
) -> bool:
    return _measured_text_height(
        content,
        width,
        font_size,
        font_family=font_family,
        use_precise=use_precise,
    ) <= height
