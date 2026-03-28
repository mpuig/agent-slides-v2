"""Heuristics for choosing a slide layout from structured content."""

from __future__ import annotations

from dataclasses import dataclass

from agent_slides.model import NodeContent
from agent_slides.model.layout_provider import LayoutProvider


@dataclass(frozen=True, slots=True)
class LayoutSuggestion:
    layout: str
    reason: str


def _priority(layout_name: str, *, body_blocks: int, image_count: int) -> int:
    if image_count > 0:
        preferred = ["image_right", "image_left", "hero_image", "gallery"]
    elif body_blocks == 0:
        preferred = ["title", "closing", "title_content", "quote"]
    elif body_blocks == 1:
        preferred = ["title_content", "title", "closing", "quote"]
    elif body_blocks == 2:
        preferred = ["two_col", "comparison", "title_content", "three_col"]
    elif body_blocks == 3:
        preferred = ["three_col", "comparison", "two_col", "title_content"]
    else:
        preferred = ["comparison", "three_col", "two_col", "title_content"]

    try:
        return preferred.index(layout_name)
    except ValueError:
        return len(preferred) + 10


def _reason(*, body_blocks: int, image_count: int, image_slots: int) -> str:
    if image_count > 0 and image_slots > 0:
        return "Image-led layout with supporting content"
    if body_blocks == 0:
        return "Heading-focused content"
    if body_blocks == 1:
        return "Single supporting content block"
    if body_blocks == 2:
        return "Two balanced content blocks"
    if body_blocks == 3:
        return "Three supporting content blocks"
    return f"{body_blocks} supporting content blocks"


def suggest_layouts(
    content: NodeContent,
    image_count: int,
    provider: LayoutProvider,
) -> list[LayoutSuggestion]:
    """Rank available layouts for the provided structured content."""

    blocks = [block for block in content.blocks if block.text.strip()]
    if not blocks:
        return []

    heading_index = next((index for index, block in enumerate(blocks) if block.type == "heading"), None)
    has_heading = heading_index is not None
    remaining_blocks = len(blocks) - (1 if has_heading else 0)

    suggestions: list[tuple[tuple[int, int, int, str], LayoutSuggestion]] = []
    for layout_name in provider.list_layouts():
        layout = provider.get_layout(layout_name)
        if layout_name == "blank" and blocks:
            continue

        roles = [slot.role for slot in layout.slots.values()]
        image_slots = sum(1 for role in roles if role == "image")
        text_slots = len(roles) - image_slots
        heading_slots = sum(1 for role in roles if role == "heading")
        remaining_text_slots = max(text_slots - (1 if heading_slots else 0), 0)

        heading_penalty = 0 if not has_heading or heading_slots > 0 else 6
        image_penalty = abs(image_slots - image_count)
        if image_count == 0 and image_slots > 0:
            image_penalty += image_slots
        body_penalty = abs(remaining_text_slots - remaining_blocks)
        waste_penalty = max(remaining_text_slots - remaining_blocks, 0)
        score = (
            heading_penalty + image_penalty + (body_penalty * 2),
            waste_penalty,
            _priority(layout_name, body_blocks=remaining_blocks, image_count=image_count),
            layout_name,
        )
        suggestions.append(
            (
                score,
                LayoutSuggestion(
                    layout=layout_name,
                    reason=_reason(
                        body_blocks=remaining_blocks,
                        image_count=image_count,
                        image_slots=image_slots,
                    ),
                ),
            )
        )

    suggestions.sort(key=lambda item: item[0])
    return [suggestion for _, suggestion in suggestions]
