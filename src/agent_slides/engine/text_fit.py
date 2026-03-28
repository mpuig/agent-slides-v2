"""Text fitting heuristics for bounded text slots."""

from __future__ import annotations

from math import ceil

AVG_CHAR_WIDTH_FACTOR = 0.6
LINE_HEIGHT_FACTOR = 1.2
SHRINK_STEP_PT = 2.0


def fit_text(
    text: str,
    width: float,
    height: float,
    default_size: float,
    min_size: float = 10.0,
) -> tuple[float, bool]:
    """Estimate a font size that fits text into a bounded area."""
    if width <= 0 or height <= 0:
        return min_size, True

    if text == "":
        return default_size, False

    if len(text) == 1:
        return default_size, False

    font_size = default_size

    while font_size > min_size:
        if _fits(text, width, height, font_size):
            return font_size, False

        font_size -= SHRINK_STEP_PT

    if _fits(text, width, height, min_size):
        return min_size, False

    return min_size, True


def _fits(text: str, width: float, height: float, font_size: float) -> bool:
    avg_char_width = AVG_CHAR_WIDTH_FACTOR * font_size

    if avg_char_width <= 0:
        return False

    chars_per_line = width / avg_char_width

    # Treat sub-character widths as one character per line to avoid division blowups.
    if chars_per_line < 1:
        lines = len(text)
    else:
        lines = ceil(len(text) / chars_per_line)

    estimated_height = lines * font_size * LINE_HEIGHT_FACTOR
    return estimated_height <= height
