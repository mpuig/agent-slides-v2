"""Rule-based layout suggestions from structured text content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_slides.model.design_rules import DesignRules, load_design_rules
from agent_slides.model.layouts import get_layout, list_layouts
from agent_slides.model.types import LayoutDef, NodeContent, TextBlock

AUTO_SUGGEST_EXCLUDED_LAYOUTS = frozenset({"closing", "quote"})


@dataclass(frozen=True)
class LayoutSuggestion:
    layout: str
    score: float
    reason: str


@dataclass(frozen=True)
class ContentProfile:
    blocks: list[TextBlock]
    block_count: int
    bullet_count: int
    word_count: int
    heading_count: int
    has_text: bool
    remaining_blocks: list[TextBlock]
    remaining_groups: list[list[TextBlock]]


@dataclass(frozen=True)
class _SuggestionRule:
    index: int
    layout: str
    score: float
    reason: str
    matches: Callable[[ContentProfile, int, DesignRules], bool]


def _analyze_content(content: NodeContent) -> ContentProfile:
    """Build a normalized content profile for layout heuristics."""

    blocks = list(content.blocks)
    remaining_blocks = blocks[1:] if blocks and blocks[0].type == "heading" else []
    return ContentProfile(
        blocks=blocks,
        block_count=len(blocks),
        bullet_count=content.bullet_count(),
        word_count=content.word_count(),
        heading_count=sum(1 for block in blocks if block.type == "heading"),
        has_text=not content.is_empty(),
        remaining_blocks=remaining_blocks,
        remaining_groups=_group_blocks_by_heading(remaining_blocks),
    )


def _group_blocks_by_heading(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Split blocks into groups that restart at each heading."""

    groups: list[list[TextBlock]] = []
    current_group: list[TextBlock] = []

    for block in blocks:
        if block.type == "heading" and current_group:
            groups.append(current_group)
            current_group = [block]
            continue
        current_group.append(block)

    if current_group:
        groups.append(current_group)

    return groups


def suggest_layouts(
    content: NodeContent,
    image_count: int = 0,
    available_layouts: list[str] | None = None,
    rules: DesignRules | None = None,
    layout_getter: Callable[[str], LayoutDef] | None = None,
) -> list[LayoutSuggestion]:
    """Return ranked layout suggestions for the given structured content."""

    design_rules = rules or load_design_rules("default")
    allowed_layouts = _allowed_layouts(available_layouts)
    if not allowed_layouts:
        return []

    profile = _analyze_content(content)
    rule_positions: dict[str, int] = {}
    suggestions: dict[str, LayoutSuggestion] = {}

    for rule in _suggestion_rules():
        if rule.layout not in allowed_layouts or rule.layout in suggestions:
            continue
        if not rule.matches(profile, image_count, design_rules):
            continue
        if image_count == 0 and _layout_requires_image(rule.layout, layout_getter):
            continue
        suggestions[rule.layout] = LayoutSuggestion(
            layout=rule.layout,
            score=rule.score,
            reason=rule.reason,
        )
        rule_positions[rule.layout] = rule.index

    return sorted(
        suggestions.values(),
        key=lambda suggestion: (-suggestion.score, rule_positions[suggestion.layout]),
    )


def _allowed_layouts(available_layouts: list[str] | None) -> set[str]:
    layouts = available_layouts or list_layouts()
    return {layout for layout in layouts if layout not in AUTO_SUGGEST_EXCLUDED_LAYOUTS}


def _suggestion_rules() -> tuple[_SuggestionRule, ...]:
    return (
        _SuggestionRule(
            index=1,
            layout="gallery",
            score=0.95,
            reason="Multiple images plus supporting text fit a gallery slide.",
            matches=lambda profile, image_count, design_rules: image_count >= 2 and profile.has_text,
        ),
        _SuggestionRule(
            index=2,
            layout="image_left",
            score=0.9,
            reason="A single image with text fits a split image-and-text slide.",
            matches=lambda profile, image_count, design_rules: image_count == 1 and profile.has_text,
        ),
        _SuggestionRule(
            index=3,
            layout="hero_image",
            score=0.9,
            reason="A single image without text fits a full-bleed hero slide.",
            matches=lambda profile, image_count, design_rules: image_count == 1 and not profile.has_text,
        ),
        _SuggestionRule(
            index=4,
            layout="blank",
            score=0.8,
            reason="Empty content should start from a blank slide.",
            matches=lambda profile, image_count, design_rules: profile.block_count == 0,
        ),
        _SuggestionRule(
            index=5,
            layout="title",
            score=0.9,
            reason="A heading with a short subtitle fits the title layout.",
            matches=lambda profile, image_count, design_rules: _matches_title(profile, design_rules),
        ),
        _SuggestionRule(
            index=6,
            layout="title_content",
            score=0.85,
            reason="A heading with one paragraph fits a title-and-content slide.",
            matches=lambda profile, image_count, design_rules: _matches_single_paragraph(profile, design_rules),
        ),
        _SuggestionRule(
            index=7,
            layout="two_col",
            score=0.9,
            reason="Two balanced content blocks fit a two-column layout.",
            matches=lambda profile, image_count, design_rules: _matches_equal_columns(profile, 2, design_rules),
        ),
        _SuggestionRule(
            index=8,
            layout="three_col",
            score=0.9,
            reason="Three balanced content blocks fit a three-column layout.",
            matches=lambda profile, image_count, design_rules: _matches_equal_columns(profile, 3, design_rules),
        ),
        _SuggestionRule(
            index=9,
            layout="comparison",
            score=0.9,
            reason="Two headed groups suggest a comparison slide.",
            matches=lambda profile, image_count, design_rules: _matches_comparison(profile),
        ),
        _SuggestionRule(
            index=10,
            layout="title_content",
            score=0.8,
            reason="A short bullet list still fits a single-column content slide.",
            matches=lambda profile, image_count, design_rules: _matches_bullets_single_column(profile, design_rules),
        ),
        _SuggestionRule(
            index=11,
            layout="two_col",
            score=0.7,
            reason="A long bullet list is easier to scan in two columns.",
            matches=lambda profile, image_count, design_rules: _matches_bullets_two_column(profile, design_rules),
        ),
        _SuggestionRule(
            index=12,
            layout="title_content",
            score=0.5,
            reason="Generic text content falls back to the title-and-content layout.",
            matches=lambda profile, image_count, design_rules: profile.has_text,
        ),
    )


def _matches_title(profile: ContentProfile, design_rules: DesignRules) -> bool:
    if profile.heading_count != 1 or len(profile.remaining_blocks) != 1:
        return False
    block = profile.remaining_blocks[0]
    if block.type != "paragraph":
        return False
    return _block_word_count(block) < design_rules.layout_hints.short_text_threshold


def _matches_single_paragraph(profile: ContentProfile, design_rules: DesignRules) -> bool:
    if profile.heading_count != 1 or len(profile.remaining_blocks) != 1:
        return False
    block = profile.remaining_blocks[0]
    if block.type != "paragraph":
        return False
    return _block_word_count(block) >= design_rules.layout_hints.short_text_threshold


def _matches_equal_columns(profile: ContentProfile, column_count: int, design_rules: DesignRules) -> bool:
    if profile.heading_count != 1 or len(profile.remaining_blocks) != column_count:
        return False
    if any(block.type != "paragraph" for block in profile.remaining_blocks):
        return False
    return _are_word_counts_balanced(
        [_block_word_count(block) for block in profile.remaining_blocks],
        design_rules.layout_hints.equal_length_threshold,
    )


def _matches_comparison(profile: ContentProfile) -> bool:
    if profile.heading_count != 3 or not profile.remaining_groups:
        return False
    if len(profile.remaining_groups) != 2:
        return False
    return all(group[0].type == "heading" for group in profile.remaining_groups)


def _matches_bullets_single_column(profile: ContentProfile, design_rules: DesignRules) -> bool:
    if not _has_heading_and_only_bullets(profile):
        return False
    bullet_count = profile.bullet_count
    return 4 <= bullet_count <= design_rules.layout_hints.max_bullets_for_single_column


def _matches_bullets_two_column(profile: ContentProfile, design_rules: DesignRules) -> bool:
    if not _has_heading_and_only_bullets(profile):
        return False
    return profile.bullet_count > design_rules.layout_hints.max_bullets_for_single_column


def _has_heading_and_only_bullets(profile: ContentProfile) -> bool:
    if profile.heading_count != 1 or not profile.remaining_blocks:
        return False
    return all(block.type == "bullet" for block in profile.remaining_blocks)


def _are_word_counts_balanced(word_counts: list[int], threshold: float) -> bool:
    if not word_counts or any(word_count == 0 for word_count in word_counts):
        return False
    return (max(word_counts) - min(word_counts)) / max(word_counts) <= threshold


def _block_word_count(block: TextBlock) -> int:
    return len(block.text.split())


def _layout_requires_image(layout_name: str, layout_getter: Callable[[str], LayoutDef] | None) -> bool:
    getter = layout_getter or get_layout
    try:
        layout = getter(layout_name)
    except Exception:
        return False
    return any(
        slot.role == "image" or ("image" in {c.casefold() for c in slot.allowed_content} and "text" not in {c.casefold() for c in slot.allowed_content})
        for slot in layout.slots.values()
    )
