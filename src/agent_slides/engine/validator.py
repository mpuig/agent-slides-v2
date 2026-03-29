"""Deck validator for design-rule constraints."""

from __future__ import annotations

from math import isclose

from agent_slides.errors import OVERFLOW, UNBOUND_NODES
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import DesignRules, FontSizeRange
from agent_slides.model.types import Deck, Node, NodeContent, Slide

MAX_SLIDES_EXCEEDED = "MAX_SLIDES_EXCEEDED"
MAX_WORDS_PER_COLUMN_EXCEEDED = "MAX_WORDS_PER_COLUMN_EXCEEDED"

# Reference area (sq pt) for a standard body column in a two-column built-in layout.
# Used to scale the max-words-per-column limit for larger template placeholders.
_REFERENCE_COLUMN_AREA_SQPT = 300.0 * 350.0  # ~105 000 sq pt
MAX_BULLETS_PER_SLIDE_EXCEEDED = "MAX_BULLETS_PER_SLIDE_EXCEEDED"
FONT_SIZE_OUT_OF_RANGE = "FONT_SIZE_OUT_OF_RANGE"
MISSING_TITLE_SLIDE = "MISSING_TITLE_SLIDE"
MISSING_CLOSING_SLIDE = "MISSING_CLOSING_SLIDE"
LAYOUT_FALLBACK = "LAYOUT_FALLBACK"


def _count_words(content: NodeContent) -> int:
    return content.word_count()


def _count_bullets(content: NodeContent) -> int:
    return content.bullet_count()


def _node_role(node: Node) -> str:
    override_role = node.style_overrides.get("role")
    if override_role in {"heading", "body", "subheading"}:
        return str(override_role)

    slot_binding = (node.slot_binding or "").lower()
    if slot_binding == "subheading":
        return "subheading"
    if "heading" in slot_binding or "title" in slot_binding:
        return "heading"
    return "body"


def _font_range_for_node(node: Node, rules: DesignRules) -> FontSizeRange:
    role = _node_role(node)
    if role == "heading":
        return rules.hierarchy.heading
    # Subheadings sit between heading and body; use the body range which
    # covers typical subheading sizes (10-18pt) without false positives.
    return rules.hierarchy.body


def _fallback_metadata(slide: Slide) -> tuple[str | None, str | None, str | None]:
    for computed in slide.computed.values():
        if computed.layout_used is None and computed.layout_overflow_reason is None:
            continue
        return (
            computed.layout_used,
            computed.layout_fallback_reason,
            computed.layout_overflow_reason,
        )
    return (None, None, None)


_TITLE_LAYOUT_SLUGS = {"title", "title_slide"}


def _is_title_layout(layout: str) -> bool:
    """Return True if *layout* looks like a title slide (built-in or template)."""
    return layout.lower() in _TITLE_LAYOUT_SLUGS


_CLOSING_LAYOUT_SLUGS = {
    "closing",
    "closing_slide",
    "statement",
    "statement_slide",
    "end",
    "d_end",
    "big_statement_green",
    "d_big_statement_green",
    "big_statement_icon",
    "d_big_statement_icon",
}


def _is_closing_layout(layout: str) -> bool:
    """Return True if *layout* looks like a closing slide (built-in or template)."""
    return layout.lower() in _CLOSING_LAYOUT_SLUGS


def validate_slide(slide: Slide, rules: DesignRules) -> list[Constraint]:
    """Validate a single slide against the provided design rules."""

    constraints: list[Constraint] = []
    layout_used, fallback_reason, overflow_reason = _fallback_metadata(slide)
    unbound_node_ids = [
        node.node_id for node in slide.nodes if node.slot_binding is None
    ]
    if unbound_node_ids:
        constraints.append(
            Constraint(
                code=UNBOUND_NODES,
                severity="error",
                message=f"Slide contains unbound nodes: {', '.join(unbound_node_ids)}.",
                slide_id=slide.slide_id,
                node_ids=unbound_node_ids,
            )
        )

    total_bullets = 0
    for node in slide.nodes:
        if node.type == "text":
            content = (
                node.content
                if isinstance(node.content, NodeContent)
                else NodeContent.model_validate(node.content)
            )
            total_bullets += _count_bullets(content)

            if node.slot_binding is not None:
                word_count = _count_words(content)
                base_limit = rules.content_limits.max_words_per_column

                # Scale limit by placeholder area when computed data is available.
                # Larger template placeholders can hold more text without visual
                # overflow, so we allow proportionally more words (capped at 2x).
                effective_limit = base_limit
                computed_node = slide.computed.get(node.node_id)
                if computed_node is not None:
                    node_area = computed_node.width * computed_node.height
                    if node_area > _REFERENCE_COLUMN_AREA_SQPT:
                        scale = min(node_area / _REFERENCE_COLUMN_AREA_SQPT, 2.0)
                        effective_limit = int(base_limit * scale)

                if word_count > effective_limit:
                    constraints.append(
                        Constraint(
                            code=MAX_WORDS_PER_COLUMN_EXCEEDED,
                            severity="warning",
                            message=(
                                f"Slot '{node.slot_binding}' has {word_count} words; "
                                f"max is {effective_limit}."
                            ),
                            slide_id=slide.slide_id,
                            node_id=node.node_id,
                        )
                    )

        computed = slide.computed.get(node.node_id)
        if computed is None or node.type != "text":
            continue

        if computed.text_overflow and isclose(
            computed.font_size_pt,
            float(rules.overflow_policy.min_font_size),
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            severity = "warning" if overflow_reason else "error"
            if overflow_reason:
                message = (
                    f"Node '{node.node_id}' still overflows at the minimum font size "
                    f"of {rules.overflow_policy.min_font_size}pt after trying layout variants; "
                    f"{overflow_reason}."
                )
            else:
                message = (
                    f"Node '{node.node_id}' still overflows at the minimum font size "
                    f"of {rules.overflow_policy.min_font_size}pt."
                )
            constraints.append(
                Constraint(
                    code=OVERFLOW,
                    severity=severity,
                    message=message,
                    slide_id=slide.slide_id,
                    node_id=node.node_id,
                )
            )

        allowed_range = _font_range_for_node(node, rules)
        if (
            not allowed_range.min_size
            <= computed.font_size_pt
            <= allowed_range.max_size
        ):
            # Template placeholders with constrained dimensions (e.g. arrow
            # title bars at ~37pt tall, divider headings at ~26pt, narrow
            # arrow columns at ~195pt wide) force the text-fit engine to
            # shrink headings below the heading-range minimum.  When the
            # placeholder is physically too small for the minimum heading
            # font size and the engine resolved without overflow, suppress
            # the warning — the result is the best fit for a constrained slot.
            role = _node_role(node)
            overflow_floor = float(rules.overflow_policy.min_font_size)
            # A placeholder is height-constrained if it can't fit two lines
            # at the minimum heading size (min_size * line_height(1.2) * 2).
            two_line_min_height = allowed_range.min_size * 1.2 * 2
            height_constrained = computed.height < two_line_min_height
            # A placeholder is width-constrained if it is narrower than ~10x
            # the minimum heading font size (roughly 10 characters at that
            # size), which forces aggressive wrapping and font shrinking.
            min_width_for_heading = allowed_range.min_size * 10
            width_constrained = computed.width < min_width_for_heading
            is_constrained_heading = (
                role == "heading"
                and computed.font_size_pt < allowed_range.min_size
                and not computed.text_overflow
                and computed.font_size_pt >= overflow_floor
                and (height_constrained or width_constrained)
            )
            if not is_constrained_heading:
                constraints.append(
                    Constraint(
                        code=FONT_SIZE_OUT_OF_RANGE,
                        severity="warning",
                        message=(
                            f"Node '{node.node_id}' font size {computed.font_size_pt:g}pt is "
                            f"outside the allowed {role} range "
                            f"{allowed_range.min_size}-{allowed_range.max_size}pt."
                        ),
                        slide_id=slide.slide_id,
                        node_id=node.node_id,
                    )
                )

    if total_bullets > rules.content_limits.max_bullets_per_slide:
        constraints.append(
            Constraint(
                code=MAX_BULLETS_PER_SLIDE_EXCEEDED,
                severity="warning",
                message=(
                    f"Slide has {total_bullets} bullets; "
                    f"max is {rules.content_limits.max_bullets_per_slide}."
                ),
                slide_id=slide.slide_id,
            )
        )

    if layout_used and layout_used != slide.layout:
        suffix = f": {fallback_reason}" if fallback_reason else "."
        constraints.append(
            Constraint(
                code=LAYOUT_FALLBACK,
                severity="warning",
                message=(
                    f"Slide used fallback layout '{layout_used}' instead of "
                    f"'{slide.layout}'{suffix}"
                ),
                slide_id=slide.slide_id,
            )
        )

    return constraints


def validate_deck(deck: Deck, rules: DesignRules) -> list[Constraint]:
    """Validate a deck and return the collected constraint violations."""

    constraints: list[Constraint] = []

    if len(deck.slides) > rules.content_limits.max_slides:
        constraints.append(
            Constraint(
                code=MAX_SLIDES_EXCEEDED,
                severity="warning",
                message=(
                    f"Deck has {len(deck.slides)} slides; "
                    f"max is {rules.content_limits.max_slides}."
                ),
            )
        )

    for slide in deck.slides:
        constraints.extend(validate_slide(slide, rules))

    if rules.deck_structure.recommend_title_slide and (
        not deck.slides or not _is_title_layout(deck.slides[0].layout)
    ):
        constraints.append(
            Constraint(
                code=MISSING_TITLE_SLIDE,
                severity="suggestion",
                message="Consider starting the deck with a title slide.",
                slide_id=deck.slides[0].slide_id if deck.slides else None,
            )
        )

    if rules.deck_structure.recommend_closing_slide and (
        not deck.slides or not _is_closing_layout(deck.slides[-1].layout)
    ):
        constraints.append(
            Constraint(
                code=MISSING_CLOSING_SLIDE,
                severity="suggestion",
                message="Consider ending the deck with a closing slide.",
                slide_id=deck.slides[-1].slide_id if deck.slides else None,
            )
        )

    return constraints
