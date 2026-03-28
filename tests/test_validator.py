from __future__ import annotations

from agent_slides.engine.validator import (
    FONT_SIZE_OUT_OF_RANGE,
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
from agent_slides.model.types import ComputedNode, Deck, Node, Slide


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


def make_computed_node(font_size_pt: float, *, overflow: bool = False) -> ComputedNode:
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


def test_validate_slide_warns_when_bullet_count_exceeds_limit() -> None:
    rules = load_design_rules("default")
    bullet_text = "\n".join(f"bullet {index}" for index in range(rules.content_limits.max_bullets_per_slide + 1))
    slide = make_slide(
        "s-1",
        "content",
        nodes=[Node(node_id="n-1", slot_binding="body", type="text", content=bullet_text)],
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
