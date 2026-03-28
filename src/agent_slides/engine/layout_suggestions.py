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


def _supporting_block_count(content: NodeContent) -> int:
    blocks = _non_empty_blocks(content)
    heading_count = sum(1 for block in blocks if getattr(block, "type", None) == "heading")
    return max(len(blocks) - min(heading_count, 1), 0)


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
    supporting_blocks = _supporting_block_count(content)
    bullet_count = content.bullet_count()
    word_count = content.word_count()
    has_heading = heading_count > 0

    suggestions: dict[str, LayoutSuggestion] = {}

    if image_count > 0:
        _add_suggestion(
            suggestions,
            layout="image_left",
            score=0.97 if block_count >= 2 or bullet_count >= 2 else 0.89,
            reason="Image-led layout with supporting content",
        )
        _add_suggestion(
            suggestions,
            layout="image_right",
            score=0.96 if block_count >= 2 or bullet_count >= 2 else 0.88,
            reason="Image-led layout with supporting content",
        )
        _add_suggestion(
            suggestions,
            layout="hero_image",
            score=0.94 if has_heading and block_count <= 2 else 0.84,
            reason="Image-led layout with supporting content",
        )
        if image_count >= 2:
            _add_suggestion(
                suggestions,
                layout="gallery",
                score=0.95 if image_count >= 4 else 0.93,
                reason="Image-led layout with supporting content",
            )

    if has_heading and block_count <= 2 and word_count <= 18:
        _add_suggestion(
            suggestions,
            layout="title",
            score=0.92,
            reason="Heading-focused content",
        )

    if block_count >= 2 or bullet_count >= 3:
        _add_suggestion(
            suggestions,
            layout="two_col",
            score=0.94 if bullet_count >= 3 else 0.89,
            reason=(
                "Two balanced content blocks"
                if supporting_blocks == 2
                else "Content splits naturally into two balanced groups."
            ),
        )

    if block_count >= 4 or bullet_count >= 5:
        _add_suggestion(
            suggestions,
            layout="comparison",
            score=0.79,
            reason=f"{supporting_blocks or block_count} supporting content blocks",
        )

    if block_count >= 5 or bullet_count >= 6:
        _add_suggestion(
            suggestions,
            layout="three_col",
            score=0.76,
            reason=(
                "Three supporting content blocks"
                if supporting_blocks == 3
                else f"{supporting_blocks or block_count} supporting content blocks"
            ),
        )

    if block_count == 2 and heading_count == 0 and word_count <= 45:
        _add_suggestion(
            suggestions,
            layout="quote",
            score=0.75,
            reason="Single supporting content block",
        )

    if block_count <= 1 and word_count <= 6:
        _add_suggestion(
            suggestions,
            layout="closing",
            score=0.7,
            reason="Heading-focused content",
        )

    _add_suggestion(
        suggestions,
        layout="title_content",
        score=0.88 if has_heading else 0.72,
        reason=(
            "Single supporting content block"
            if supporting_blocks <= 1
            else f"{supporting_blocks} supporting content blocks"
        ),
    )

    if not suggestions:
        _add_suggestion(
            suggestions,
            layout="title_content",
            score=0.7,
            reason="Single supporting content block",
        )

    ranked = sorted(suggestions.values(), key=lambda item: (-item.score, item.layout))
    return ranked[:limit]


def serialize_suggestions(suggestions: list[LayoutSuggestion]) -> list[dict[str, object]]:
    """Convert suggestions to JSON-safe dictionaries."""

    return [asdict(suggestion) for suggestion in suggestions]
