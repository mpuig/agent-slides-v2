from __future__ import annotations

from agent_slides.engine.validator import (
    FONT_SIZE_OUT_OF_RANGE,
    LAYOUT_FALLBACK,
    MAX_BULLETS_PER_SLIDE_EXCEEDED,
    MAX_SLIDES_EXCEEDED,
    MAX_WORDS_PER_COLUMN_EXCEEDED,
    MISSING_CLOSING_SLIDE,
    MISSING_TITLE_SLIDE,
    validate_deck,
    validate_slide,
)
from agent_slides.errors import OVERFLOW, UNBOUND_NODES
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.types import ComputedNode, Deck, Node, NodeContent, Slide, TextBlock


def make_slide(
    slide_id: str,
    layout: str,
    nodes: list[Node] | None = None,
    computed: dict[str, ComputedNode] | None = None,
) -> Slide:
    return Slide(
        slide_id=slide_id,
        layout=layout,
        nodes=nodes or [],
        computed=computed or {},
    )


def make_computed_node(
    font_size_pt: float,
    *,
    overflow: bool = False,
    layout_used: str | None = None,
    fallback_reason: str | None = None,
    overflow_reason: str | None = None,
) -> ComputedNode:
    return ComputedNode(
        x=72.0,
        y=54.0,
        width=576.0,
        height=80.0,
        font_size_pt=font_size_pt,
        font_family="Aptos",
        color="#333333",
        bg_color="#FFFFFF",
        font_bold=False,
        text_overflow=overflow,
        layout_used=layout_used,
        layout_fallback_reason=fallback_reason,
        layout_overflow_reason=overflow_reason,
        revision=1,
    )


def make_deck(slides: list[Slide]) -> Deck:
    return Deck(deck_id="deck-1", slides=slides)


def test_clean_deck_has_no_constraints() -> None:
    rules = load_design_rules("default")
    deck = make_deck(
        [
            make_slide(
                "s-1",
                "title",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Deck title")
                ],
                computed={"n-1": make_computed_node(28.0)},
            ),
            make_slide(
                "s-2",
                "closing",
                nodes=[
                    Node(node_id="n-2", slot_binding="body", type="text", content="Thanks")
                ],
                computed={"n-2": make_computed_node(14.0)},
            ),
        ]
    )

    assert validate_deck(deck, rules) == []


def test_validate_slide_returns_overflow_constraint_with_error_severity() -> None:
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content="Overflowing text")],
        computed={"n-1": make_computed_node(rules.overflow_policy.min_font_size, overflow=True)},
    )

    constraints = validate_slide(slide, rules)

    assert len(constraints) == 1
    assert constraints[0].code == OVERFLOW
    assert constraints[0].severity == "error"
    assert constraints[0].slide_id == "s-1"
    assert constraints[0].node_id == "n-1"


def test_validate_slide_downgrades_overflow_after_variant_attempts() -> None:
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content="Overflowing text")],
        computed={
            "n-1": make_computed_node(
                rules.overflow_policy.min_font_size,
                overflow=True,
                overflow_reason="text overflow in body",
            )
        },
    )

    constraints = validate_slide(slide, rules)

    assert len(constraints) == 1
    assert constraints[0].code == OVERFLOW
    assert constraints[0].severity == "warning"
    assert "after trying layout variants" in constraints[0].message


def test_validate_slide_returns_unbound_nodes_constraint_with_node_ids() -> None:
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "content",
        nodes=[
            Node(node_id="n-1", slot_binding=None, type="text", content="Loose"),
            Node(node_id="n-2", slot_binding=None, type="text", content="Still loose"),
        ],
    )

    constraints = validate_slide(slide, rules)

    assert len(constraints) == 1
    assert constraints[0].code == UNBOUND_NODES
    assert constraints[0].severity == "error"
    assert constraints[0].node_ids == ["n-1", "n-2"]


def test_validate_deck_warns_when_slide_count_exceeds_limit() -> None:
    rules = load_design_rules("default")
    slides = [
        make_slide(
            f"s-{index}",
            "content",
            nodes=[Node(node_id=f"n-{index}", slot_binding="body", type="text", content="Body")],
            computed={f"n-{index}": make_computed_node(14.0)},
        )
        for index in range(1, rules.content_limits.max_slides + 2)
    ]

    constraints = validate_deck(make_deck(slides), rules)
    max_slides_constraint = next(
        constraint for constraint in constraints if constraint.code == MAX_SLIDES_EXCEEDED
    )

    assert max_slides_constraint.severity == "warning"


def test_validate_slide_warns_when_slot_word_count_exceeds_limit() -> None:
    rules = load_design_rules("default")
    content = "word " * (rules.content_limits.max_words_per_column + 1)
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content=content.strip())],
        computed={"n-1": make_computed_node(14.0)},
    )

    constraints = validate_slide(slide, rules)
    word_limit_constraint = next(
        constraint
        for constraint in constraints
        if constraint.code == MAX_WORDS_PER_COLUMN_EXCEEDED
    )

    assert word_limit_constraint.severity == "warning"
    assert word_limit_constraint.node_id == "n-1"


def test_validate_slide_scales_word_limit_by_placeholder_area() -> None:
    """Large template placeholders allow more words proportionally."""
    rules = load_design_rules("default")
    base_limit = rules.content_limits.max_words_per_column  # 50
    # 55 words exceeds the base limit but not the scaled limit for a large placeholder
    content = "word " * 55

    # Large placeholder: 600x400 = 240,000 sq pt (~2.3x reference area of 105,000)
    # Scaling is capped at 2x, so effective limit = 100 words
    large_computed = ComputedNode(
        x=60.0, y=70.0, width=600.0, height=400.0,
        font_size_pt=14.0, font_family="Aptos", color="#333333",
        bg_color="#FFFFFF", font_bold=False, text_overflow=False, revision=1,
    )
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content=content.strip())],
        computed={"n-1": large_computed},
    )
    constraints = validate_slide(slide, rules)
    assert all(c.code != MAX_WORDS_PER_COLUMN_EXCEEDED for c in constraints), (
        f"55 words should be allowed in a large placeholder (base limit={base_limit})"
    )

    # Small placeholder should still flag the same content
    small_computed = ComputedNode(
        x=60.0, y=70.0, width=300.0, height=200.0,
        font_size_pt=14.0, font_family="Aptos", color="#333333",
        bg_color="#FFFFFF", font_bold=False, text_overflow=False, revision=1,
    )
    slide_small = make_slide(
        "s-2",
        "content",
        nodes=[Node(node_id="n-2", slot_binding="body", type="text", content=content.strip())],
        computed={"n-2": small_computed},
    )
    constraints_small = validate_slide(slide_small, rules)
    assert any(c.code == MAX_WORDS_PER_COLUMN_EXCEEDED for c in constraints_small), (
        f"55 words should be flagged in a small placeholder (base limit={base_limit})"
    )


def test_validate_slide_warns_when_bullet_count_exceeds_limit() -> None:
    rules = load_design_rules("default")
    bullet_content = NodeContent(
        blocks=[
            TextBlock(type="bullet", text=f"bullet {index}")
            for index in range(rules.content_limits.max_bullets_per_slide + 1)
        ]
    )
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content=bullet_content)],
        computed={"n-1": make_computed_node(14.0)},
    )

    constraints = validate_slide(slide, rules)
    bullet_constraint = next(
        constraint
        for constraint in constraints
        if constraint.code == MAX_BULLETS_PER_SLIDE_EXCEEDED
    )

    assert bullet_constraint.severity == "warning"
    assert bullet_constraint.slide_id == "s-1"


def test_validate_slide_does_not_treat_legacy_paragraph_lines_as_bullets() -> None:
    rules = load_design_rules("default")
    text = "\n\n".join(f"Paragraph {index}" for index in range(rules.content_limits.max_bullets_per_slide + 1))
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content=text)],
        computed={"n-1": make_computed_node(14.0)},
    )

    constraints = validate_slide(slide, rules)

    assert all(constraint.code != MAX_BULLETS_PER_SLIDE_EXCEEDED for constraint in constraints)


def test_validate_slide_warns_when_font_size_is_outside_hierarchy_range() -> None:
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="heading", type="text", content="Heading")],
        computed={"n-1": make_computed_node(20.0)},
    )

    constraints = validate_slide(slide, rules)
    hierarchy_constraint = next(
        constraint for constraint in constraints if constraint.code == FONT_SIZE_OUT_OF_RANGE
    )

    assert hierarchy_constraint.severity == "warning"
    assert hierarchy_constraint.node_id == "n-1"


def test_validate_slide_reports_layout_fallback_warning() -> None:
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "image_left",
        nodes=[
            Node(node_id="n-1", slot_binding="heading", type="text", content="Heading"),
            Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
        ],
        computed={
            "n-1": make_computed_node(
                28.0,
                layout_used="image_right",
                fallback_reason="Forced primary failure",
            ),
            "n-2": make_computed_node(
                18.0,
                layout_used="image_right",
                fallback_reason="Forced primary failure",
            ),
        },
    )

    constraints = validate_slide(slide, rules)
    fallback = next(constraint for constraint in constraints if constraint.code == LAYOUT_FALLBACK)

    assert fallback.severity == "warning"
    assert "image_right" in fallback.message
    assert "image_left" in fallback.message


def test_validate_deck_adds_structure_suggestions() -> None:
    rules = load_design_rules("default")
    deck = make_deck(
        [
            make_slide(
                "s-1",
                "content",
                nodes=[Node(node_id="n-1", slot_binding="body", type="text", content="Intro")],
                computed={"n-1": make_computed_node(14.0)},
            )
        ]
    )

    constraints = validate_deck(deck, rules)

    title_constraint = next(
        constraint for constraint in constraints if constraint.code == MISSING_TITLE_SLIDE
    )
    closing_constraint = next(
        constraint for constraint in constraints if constraint.code == MISSING_CLOSING_SLIDE
    )

    assert title_constraint.severity == "suggestion"
    assert closing_constraint.severity == "suggestion"


def test_validate_deck_recognizes_template_title_slug() -> None:
    """Template slug 'title_slide' should satisfy the title-slide check."""
    rules = load_design_rules("default")
    deck = make_deck(
        [
            make_slide(
                "s-1",
                "title_slide",
                nodes=[Node(node_id="n-1", slot_binding="heading", type="text", content="Title")],
                computed={"n-1": make_computed_node(36.0)},
            ),
            make_slide(
                "s-2",
                "end",
                nodes=[Node(node_id="n-2", slot_binding="body", type="text", content="End")],
                computed={"n-2": make_computed_node(14.0)},
            ),
        ]
    )

    constraints = validate_deck(deck, rules)
    assert all(c.code != MISSING_TITLE_SLIDE for c in constraints)
    assert all(c.code != MISSING_CLOSING_SLIDE for c in constraints)


def test_validate_slide_subheading_uses_body_range() -> None:
    """Subheading-bound nodes should not be flagged at body-range font sizes."""
    rules = load_design_rules("default")
    slide = make_slide(
        "s-1",
        "title_slide",
        nodes=[
            Node(node_id="n-1", slot_binding="subheading", type="text", content="Sub")
        ],
        computed={"n-1": make_computed_node(16.0)},
    )

    constraints = validate_slide(slide, rules)
    assert all(c.code != FONT_SIZE_OUT_OF_RANGE for c in constraints)


def test_validate_slide_suppresses_font_size_for_constrained_heading() -> None:
    """Headings in physically short placeholders (< 2 lines at min size) should not
    trigger FONT_SIZE_OUT_OF_RANGE when text fitting shrinks without overflow."""
    rules = load_design_rules("default")
    # Placeholder height 37pt is too short for 24pt heading min (needs 57.6pt for 2 lines)
    short_computed = ComputedNode(
        x=72.0, y=54.0, width=493.0, height=37.0,
        font_size_pt=20.0, font_family="Aptos", color="#333333",
        font_bold=False, text_overflow=False, revision=1,
    )
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="heading", type="text", content="Title")],
        computed={"n-1": short_computed},
    )

    constraints = validate_slide(slide, rules)
    assert all(c.code != FONT_SIZE_OUT_OF_RANGE for c in constraints)


def test_validate_slide_flags_font_size_for_normal_height_heading() -> None:
    """Headings in normal-height placeholders should still trigger FONT_SIZE_OUT_OF_RANGE
    even when font size is below the heading minimum."""
    rules = load_design_rules("default")
    # Placeholder height 80pt is tall enough for heading min (needs 57.6pt)
    normal_computed = ComputedNode(
        x=72.0, y=54.0, width=576.0, height=80.0,
        font_size_pt=20.0, font_family="Aptos", color="#333333",
        font_bold=False, text_overflow=False, revision=1,
    )
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="heading", type="text", content="Title")],
        computed={"n-1": normal_computed},
    )

    constraints = validate_slide(slide, rules)
    font_constraint = next(c for c in constraints if c.code == FONT_SIZE_OUT_OF_RANGE)
    assert font_constraint.severity == "warning"
