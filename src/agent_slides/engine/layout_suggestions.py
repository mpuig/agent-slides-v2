"""Compatibility wrapper for layout suggestions."""

from __future__ import annotations

from dataclasses import asdict

from agent_slides.engine.layout_suggest import LayoutSuggestion, suggest_layouts as suggest_layouts_for_content
from agent_slides.model.design_rules import DesignRules
from agent_slides.model.types import NodeContent


def suggest_layouts(
    content: NodeContent,
    *,
    image_count: int = 0,
    limit: int = 3,
    available_layouts: list[str] | None = None,
    rules: DesignRules | None = None,
) -> list[LayoutSuggestion]:
    """Return ranked layout suggestions, preserving the CLI-facing API."""

    return suggest_layouts_for_content(
        content,
        image_count=image_count,
        available_layouts=available_layouts,
        rules=rules,
    )[:limit]


def serialize_suggestions(suggestions: list[LayoutSuggestion]) -> list[dict[str, object]]:
    """Convert suggestions to JSON-safe dictionaries."""

    return [asdict(suggestion) for suggestion in suggestions]
