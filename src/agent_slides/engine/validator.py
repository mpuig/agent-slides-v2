"""Deck validator for design-rule constraints."""

from __future__ import annotations

from math import isclose

from agent_slides.errors import OVERFLOW, UNBOUND_NODES
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import DesignRules, FontSizeRange
from agent_slides.model.types import Deck, Node, NodeContent, Slide

MAX_SLIDES_EXCEEDED = "MAX_SLIDES_EXCEEDED"
MAX_WORDS_PER_COLUMN_EXCEEDED = "MAX_WORDS_PER_COLUMN_EXCEEDED"
MAX_BULLETS_PER_SLIDE_EXCEEDED = "MAX_BULLETS_PER_SLIDE_EXCEEDED"
FONT_SIZE_OUT_OF_RANGE = "FONT_SIZE_OUT_OF_RANGE"
MISSING_TITLE_SLIDE = "MISSING_TITLE_SLIDE"
MISSING_CLOSING_SLIDE = "MISSING_CLOSING_SLIDE"


def _count_words(content: NodeContent) -> int:
    return content.word_count()


def _count_bullets(content: NodeContent) -> int:
    return content.bullet_count()


def _node_role(node: Node) -> str:
    override_role = node.style_overrides.get("role")
    if override_role in {"heading", "body"}:
        return str(override_role)

    slot_binding = (node.slot_binding or "").lower()
    if "heading" in slot_binding or "title" in slot_binding:
        return "heading"
    return "body"


def _font_range_for_node(node: Node, rules: DesignRules) -> FontSizeRange:
    if _node_role(node) == "heading":
        return rules.hierarchy.heading
    return rules.hierarchy.body


def validate_slide(slide: Slide, rules: DesignRules) -> list[Constraint]:
    """Validate a single slide against the provided design rules."""

    constraints: list[Constraint] = []
    unbound_node_ids = [node.node_id for node in slide.nodes if node.slot_binding is None]
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
        if node.type == "image":
            continue

        total_bullets += _count_bullets(node.content)

        if node.slot_binding is not None:
            word_count = _count_words(node.content)
            if word_count > rules.content_limits.max_words_per_column:
                constraints.append(
                    Constraint(
                        code=MAX_WORDS_PER_COLUMN_EXCEEDED,
                        severity="warning",
                        message=(
                            f"Slot '{node.slot_binding}' has {word_count} words; "
                            f"max is {rules.content_limits.max_words_per_column}."
                        ),
                        slide_id=slide.slide_id,
                        node_id=node.node_id,
                    )
                )

        computed = slide.computed.get(node.node_id)
        if computed is None:
            continue

        if computed.text_overflow and isclose(
            computed.font_size_pt,
            float(rules.overflow_policy.min_font_size),
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            constraints.append(
                Constraint(
                    code=OVERFLOW,
                    severity="error",
                    message=(
                        f"Node '{node.node_id}' still overflows at the minimum font size "
                        f"of {rules.overflow_policy.min_font_size}pt."
                    ),
                    slide_id=slide.slide_id,
                    node_id=node.node_id,
                )
            )

        allowed_range = _font_range_for_node(node, rules)
        if not allowed_range.min_size <= computed.font_size_pt <= allowed_range.max_size:
            constraints.append(
                Constraint(
                    code=FONT_SIZE_OUT_OF_RANGE,
                    severity="warning",
                    message=(
                        f"Node '{node.node_id}' font size {computed.font_size_pt:g}pt is "
                        f"outside the allowed {_node_role(node)} range "
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
        not deck.slides or deck.slides[0].layout != "title"
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
        not deck.slides or deck.slides[-1].layout != "closing"
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
