"""Heuristics for recommending built-in layouts from structured content."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from agent_slides.model.types import NodeContent


@dataclass(frozen=True)
class LayoutSuggestion:
    layout: str
    score: float
    reason: str


def _non_empty_blocks(content: NodeContent) -> list[object]:
    return [block for block in content.blocks if block.text.strip()]


def _add_suggestion(
    suggestions: dict[str, LayoutSuggestion],
    *,
    layout: str,
    score: float,
    reason: str,
) -> None:
    candidate = LayoutSuggestion(layout=layout, score=round(score, 2), reason=reason)
    current = suggestions.get(layout)
    if current is None or candidate.score > current.score:
        suggestions[layout] = candidate


def suggest_layouts(content: NodeContent, *, image_count: int = 0, limit: int = 3) -> list[LayoutSuggestion]:
    """Return ranked built-in layout suggestions for the provided content."""

    blocks = _non_empty_blocks(content)
    block_count = len(blocks)
    heading_count = sum(1 for block in blocks if getattr(block, "type", None) == "heading")
    bullet_count = content.bullet_count()
    word_count = content.word_count()
    has_heading = heading_count > 0

    suggestions: dict[str, LayoutSuggestion] = {}

    if image_count > 0:
        _add_suggestion(
            suggestions,
            layout="image_left",
            score=0.97 if block_count >= 2 or bullet_count >= 2 else 0.89,
            reason="Image plus supporting text fits a side-by-side layout.",
        )
        _add_suggestion(
            suggestions,
            layout="image_right",
            score=0.96 if block_count >= 2 or bullet_count >= 2 else 0.88,
            reason="A mirrored side-by-side layout also suits image-backed content.",
        )
        _add_suggestion(
            suggestions,
            layout="hero_image",
            score=0.94 if has_heading and block_count <= 2 else 0.84,
            reason="A strong headline with imagery can work as a hero slide.",
        )
        if image_count >= 2:
            _add_suggestion(
                suggestions,
                layout="gallery",
                score=0.95 if image_count >= 4 else 0.93,
                reason="Multiple images can be grouped into a gallery treatment.",
            )

    if has_heading and block_count <= 2 and word_count <= 18:
        _add_suggestion(
            suggestions,
            layout="title",
            score=0.92,
            reason="Short heading-led content fits a title slide.",
        )

    if block_count >= 2 or bullet_count >= 3:
        _add_suggestion(
            suggestions,
            layout="two_col",
            score=0.94 if bullet_count >= 3 else 0.89,
            reason="Content splits naturally into two balanced groups.",
        )

    if block_count >= 4 or bullet_count >= 5:
        _add_suggestion(
            suggestions,
            layout="comparison",
            score=0.79,
            reason="Several supporting points could be framed as a comparison.",
        )

    if block_count >= 5 or bullet_count >= 6:
        _add_suggestion(
            suggestions,
            layout="three_col",
            score=0.76,
            reason="Denser content may benefit from a three-column scan pattern.",
        )

    if block_count == 2 and heading_count == 0 and word_count <= 45:
        _add_suggestion(
            suggestions,
            layout="quote",
            score=0.75,
            reason="A main statement plus attribution could read well as a quote slide.",
        )

    if block_count <= 1 and word_count <= 6:
        _add_suggestion(
            suggestions,
            layout="closing",
            score=0.7,
            reason="Very short content can work as a closing slide.",
        )

    _add_suggestion(
        suggestions,
        layout="title_content",
        score=0.88 if has_heading else 0.72,
        reason="A single-column title and body layout is a safe baseline fit.",
    )

    if not suggestions:
        _add_suggestion(
            suggestions,
            layout="title_content",
            score=0.7,
            reason="Defaulting to a flexible single-column layout.",
        )

    ranked = sorted(suggestions.values(), key=lambda item: (-item.score, item.layout))
    return ranked[:limit]


def serialize_suggestions(suggestions: list[LayoutSuggestion]) -> list[dict[str, object]]:
    """Convert suggestions to JSON-safe dictionaries."""

    return [asdict(suggestion) for suggestion in suggestions]
