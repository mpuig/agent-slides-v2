"""Text fitting heuristics for bounded text slots."""

from __future__ import annotations

import re

from PIL import ImageFont

from agent_slides.model.types import NodeContent, TextBlock, TextRun, split_text_runs_by_line

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
ICON_GLYPH_WIDTH_FACTOR = 1.4
ICON_GAP_WIDTH_FACTOR = 0.45
TOKEN_PATTERN = re.compile(r"\s+|\S+")


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


def _estimate_text_width(text: str, font_size: float, *, font_family: str | None) -> float:
    if text == "":
        return 0.0
    return len(text) * _width_factor(font_family) * font_size


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


def _effective_run_font_size(block: TextBlock, font_size: float, run: TextRun) -> float:
    if run.font_size is not None:
        return run.font_size
    return font_size * _font_size_factor(block)


def _tokenize_runs(runs: list[TextRun]) -> list[TextRun]:
    tokens: list[TextRun] = []
    for run in runs:
        parts = TOKEN_PATTERN.findall(run.text) or [run.text]
        for part in parts:
            tokens.append(run.model_copy(update={"text": part}))
    return tokens


def _measure_run_width(
    run: TextRun,
    *,
    font_family: str | None,
    font_size: float,
    block: TextBlock,
    use_precise: bool,
    font_cache: dict[float, ImageFont.ImageFont],
) -> float:
    effective_size = _effective_run_font_size(block, font_size, run)
    if use_precise:
        font = font_cache.get(effective_size)
        if font is None:
            font = _load_precise_font(font_family, effective_size)
            font_cache[effective_size] = font
        return _measure_precise_width(run.text, font)
    return _estimate_text_width(run.text, effective_size, font_family=font_family)


def _break_long_token(
    token: TextRun,
    width: float,
    *,
    font_family: str | None,
    font_size: float,
    block: TextBlock,
    use_precise: bool,
    font_cache: dict[float, ImageFont.ImageFont],
) -> list[TextRun]:
    parts: list[TextRun] = []
    current = ""

    for character in token.text:
        candidate = f"{current}{character}"
        candidate_run = token.model_copy(update={"text": candidate})
        if current and _measure_run_width(
            candidate_run,
            font_family=font_family,
            font_size=font_size,
            block=block,
            use_precise=use_precise,
            font_cache=font_cache,
        ) > width:
            parts.append(token.model_copy(update={"text": current}))
            current = character
        else:
            current = candidate

    if current:
        parts.append(token.model_copy(update={"text": current}))
    return parts or [token]


def _wrap_line_runs(
    line_runs: list[TextRun],
    width: float,
    *,
    font_size: float,
    block: TextBlock,
    font_family: str | None,
    use_precise: bool,
    font_cache: dict[float, ImageFont.ImageFont],
) -> list[list[TextRun]]:
    if not line_runs:
        return [[TextRun(text="")]]

    tokens = _tokenize_runs(line_runs)
    wrapped: list[list[TextRun]] = []
    current: list[TextRun] = []
    current_width = 0.0
    def finish_line() -> None:
        nonlocal current, current_width
        while current and current[-1].text.isspace():
            current.pop()
        wrapped.append(current or [TextRun(text="")])
        current = []
        current_width = 0.0

    for token in tokens:
        if token.text.isspace() and not current:
            continue

        token_width = _measure_run_width(
            token,
            font_family=font_family,
            font_size=font_size,
            block=block,
            use_precise=use_precise,
            font_cache=font_cache,
        )

        if token_width > width and not token.text.isspace():
            if current:
                finish_line()
            for chunk in _break_long_token(
                token,
                width,
                font_family=font_family,
                font_size=font_size,
                block=block,
                use_precise=use_precise,
                font_cache=font_cache,
            ):
                chunk_width = _measure_run_width(
                    chunk,
                    font_family=font_family,
                    font_size=font_size,
                    block=block,
                    use_precise=use_precise,
                    font_cache=font_cache,
                )
                if current and current_width + chunk_width > width:
                    finish_line()
                current.append(chunk)
                current_width += chunk_width
            continue

        if current and current_width + token_width > width:
            finish_line()
            if token.text.isspace():
                continue

        current.append(token)
        current_width += token_width

    if current or not wrapped:
        finish_line()

    return wrapped


def _line_height(
    line_runs: list[TextRun],
    *,
    block: TextBlock,
    font_size: float,
    font_family: str | None,
    use_precise: bool,
    font_cache: dict[float, ImageFont.ImageFont],
) -> float:
    if use_precise:
        heights = []
        for run in line_runs:
            effective_size = _effective_run_font_size(block, font_size, run)
            font = font_cache.get(effective_size)
            if font is None:
                font = _load_precise_font(font_family, effective_size)
                font_cache[effective_size] = font
            heights.append(_measure_precise_line_height(font))
        base_height = max(heights or [font_size * _font_size_factor(block)])
    else:
        sizes = [_effective_run_font_size(block, font_size, run) for run in line_runs if run.text]
        base_height = max(sizes or [font_size * _font_size_factor(block)])

    return base_height * _line_height_factor(block)


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
    font_cache: dict[float, ImageFont.ImageFont] = {}

    for index, block in enumerate(blocks):
        block_width = _block_width(width, block, font_size, font_family=font_family)
        for line_runs in split_text_runs_by_line(block):
            wrapped_lines = _wrap_line_runs(
                line_runs,
                block_width,
                font_size=font_size,
                block=block,
                font_family=font_family,
                use_precise=use_precise,
                font_cache=font_cache,
            )
            lines_height += sum(
                _line_height(
                    visual_line,
                    block=block,
                    font_size=font_size,
                    font_family=font_family,
                    use_precise=use_precise,
                    font_cache=font_cache,
                )
                for visual_line in wrapped_lines
            )
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
