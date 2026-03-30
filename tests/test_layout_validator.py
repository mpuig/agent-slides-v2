from __future__ import annotations

from agent_slides.engine.constraints import Rect
from agent_slides.engine.layout_validator import (
    GUTTER_MISMATCH,
    PEER_TOP_MISMATCH,
    PEER_WIDTH_MISMATCH,
    SAFE_MARGIN_VIOLATION,
    SLOT_OVERLAP,
    TEXT_OVERFLOW,
    validate_layout,
)
from agent_slides.engine.reflow import reflow_deck, reflow_slide
from agent_slides.model import (
    ComputedNode,
    Counters,
    Deck,
    GridDef,
    LayoutDef,
    Node,
    Slide,
    SlotDef,
    TextFitting,
)
from agent_slides.model.themes import load_theme


def _layout(slots: dict[str, SlotDef]) -> LayoutDef:
    return LayoutDef(
        name="custom",
        slots=slots,
        grid=GridDef(
            columns=1,
            rows=1,
            row_heights=[1.0],
            col_widths=[1.0],
            margin=0.0,
            gutter=0.0,
        ),
        text_fitting={
            "heading": TextFitting(default_size=32.0, min_size=24.0),
            "body": TextFitting(default_size=18.0, min_size=10.0),
        },
    )


def _body_slot(
    *, x: float, y: float, width: float, height: float, peer_group: str = "columns"
) -> SlotDef:
    return SlotDef(
        grid_row=1,
        grid_col=1,
        role="body",
        peer_group=peer_group,
        alignment_group="content",
        x=x,
        y=y,
        width=width,
        height=height,
    )


def test_validate_layout_checks_peer_top_alignment_with_epsilon() -> None:
    layout = _layout(
        {
            "col1": _body_slot(x=60.0, y=120.0, width=180.0, height=220.0),
            "col2": _body_slot(x=260.0, y=121.5, width=180.0, height=220.0),
        }
    )

    within_epsilon = validate_layout(
        layout,
        {
            "col1": Rect(x=60.0, y=120.0, width=180.0, height=220.0),
            "col2": Rect(x=260.0, y=120.5, width=180.0, height=220.0),
        },
        epsilon=1.0,
    )
    beyond_epsilon = validate_layout(
        layout,
        {
            "col1": Rect(x=60.0, y=120.0, width=180.0, height=220.0),
            "col2": Rect(x=260.0, y=122.5, width=180.0, height=220.0),
        },
        epsilon=1.0,
    )

    assert within_epsilon == []
    assert [violation.code for violation in beyond_epsilon] == [PEER_TOP_MISMATCH]
    assert beyond_epsilon[0].slot_refs == ("col1", "col2")


def test_validate_layout_checks_peer_widths() -> None:
    layout = _layout(
        {
            "col1": _body_slot(x=60.0, y=120.0, width=180.0, height=220.0),
            "col2": _body_slot(x=260.0, y=120.0, width=188.0, height=220.0),
        }
    )

    violations = validate_layout(
        layout,
        {
            "col1": Rect(x=60.0, y=120.0, width=180.0, height=220.0),
            "col2": Rect(x=260.0, y=120.0, width=188.0, height=220.0),
        },
    )

    assert [violation.code for violation in violations] == [PEER_WIDTH_MISMATCH]
    assert violations[0].slot_refs == ("col1", "col2")


def test_validate_layout_checks_consistent_gutters() -> None:
    layout = _layout(
        {
            "col1": _body_slot(x=60.0, y=120.0, width=160.0, height=220.0),
            "col2": _body_slot(x=240.0, y=120.0, width=160.0, height=220.0),
            "col3": _body_slot(x=432.0, y=120.0, width=160.0, height=220.0),
        }
    )

    violations = validate_layout(
        layout,
        {
            "col1": Rect(x=60.0, y=120.0, width=160.0, height=220.0),
            "col2": Rect(x=240.0, y=120.0, width=160.0, height=220.0),
            "col3": Rect(x=432.0, y=120.0, width=160.0, height=220.0),
        },
    )

    assert [violation.code for violation in violations] == [GUTTER_MISMATCH]
    assert violations[0].slot_refs == ("col1", "col2", "col3")


def test_validate_layout_checks_bounds_and_overlap_edges() -> None:
    layout = _layout(
        {
            "left": _body_slot(
                x=-8.0, y=40.0, width=180.0, height=220.0, peer_group="cards"
            ),
            "center": _body_slot(
                x=172.0, y=40.0, width=180.0, height=220.0, peer_group="cards"
            ),
            "right": _body_slot(
                x=340.0, y=40.0, width=180.0, height=220.0, peer_group="cards"
            ),
        }
    )

    violations = validate_layout(
        layout,
        {
            "left": Rect(x=-8.0, y=40.0, width=180.0, height=220.0),
            "center": Rect(x=172.0, y=40.0, width=180.0, height=220.0),
            "right": Rect(x=352.0, y=40.0, width=180.0, height=220.0),
        },
    )

    assert [violation.code for violation in violations] == [SAFE_MARGIN_VIOLATION]

    touching_only = validate_layout(
        layout,
        {
            "left": Rect(x=20.0, y=40.0, width=160.0, height=220.0),
            "center": Rect(x=180.0, y=40.0, width=160.0, height=220.0),
            "right": Rect(x=340.0, y=40.0, width=180.0, height=220.0),
        },
    )
    assert all(violation.code != SLOT_OVERLAP for violation in touching_only)

    overlapping = validate_layout(
        layout,
        {
            "left": Rect(x=20.0, y=40.0, width=180.0, height=220.0),
            "center": Rect(x=180.0, y=40.0, width=180.0, height=220.0),
            "right": Rect(x=380.0, y=40.0, width=180.0, height=220.0),
        },
    )
    assert SLOT_OVERLAP in [violation.code for violation in overlapping]


def test_validate_layout_reports_explicit_text_overflow() -> None:
    layout = _layout(
        {
            "body": _body_slot(
                x=60.0, y=120.0, width=420.0, height=120.0, peer_group="body"
            )
        }
    )

    violations = validate_layout(
        layout,
        {"body": Rect(x=60.0, y=120.0, width=420.0, height=120.0)},
        computed_by_slot={
            "body": ComputedNode(
                x=60.0,
                y=120.0,
                width=420.0,
                height=120.0,
                font_size_pt=10.0,
                font_family="Calibri",
                color="#000000",
                revision=0,
                text_overflow=True,
                content_type="text",
            )
        },
    )

    assert [violation.code for violation in violations] == [TEXT_OVERFLOW]
    assert violations[0].slot_refs == ("body",)


def test_reflow_slide_returns_layout_validator_errors() -> None:
    layout = _layout(
        {
            "left": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                peer_group="columns",
                alignment_group="content",
                x=60.0,
                y=140.0,
                width=180.0,
                height=220.0,
            ),
            "right": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                peer_group="columns",
                alignment_group="content",
                x=270.0,
                y=154.0,
                width=196.0,
                height=220.0,
            ),
        }
    )
    slide = Slide(
        slide_id="s-1",
        layout="custom",
        nodes=[
            Node(
                node_id="n-1", slot_binding="left", type="text", content="Left column"
            ),
            Node(
                node_id="n-2", slot_binding="right", type="text", content="Right column"
            ),
        ],
    )

    violations = reflow_slide(slide, layout, load_theme("default"))

    assert {violation.code for violation in violations} == {
        PEER_TOP_MISMATCH,
        PEER_WIDTH_MISMATCH,
    }


class _SingleLayoutProvider:
    def __init__(self, layout: LayoutDef) -> None:
        self._layout = layout

    def get_layout(self, slug: str) -> LayoutDef:
        assert slug == self._layout.name
        return self._layout

    def list_layouts(self) -> list[str]:
        return [self._layout.name]

    def get_slot_names(self, slug: str) -> list[str]:
        return list(self.get_layout(slug).slots)

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        return self.get_layout(slug).text_fitting[role]

    def get_variants(self, slug: str) -> list[LayoutDef]:
        self.get_layout(slug)
        return []


def test_reflow_deck_returns_validator_errors_by_slide() -> None:
    layout = _layout(
        {
            "left": _body_slot(x=60.0, y=120.0, width=180.0, height=220.0),
            "right": _body_slot(x=260.0, y=134.0, width=196.0, height=220.0),
        }
    ).model_copy(update={"name": "custom"})
    deck = Deck(
        deck_id="deck-invalid",
        slides=[
            Slide(
                slide_id="s-1",
                layout="custom",
                nodes=[
                    Node(
                        node_id="n-1", slot_binding="left", type="text", content="Left"
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="right",
                        type="text",
                        content="Right",
                    ),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )

    violations_by_slide = reflow_deck(deck, provider=_SingleLayoutProvider(layout))

    assert set(violations_by_slide) == {"s-1"}
    assert {violation.code for violation in violations_by_slide["s-1"]} == {
        PEER_TOP_MISMATCH,
        PEER_WIDTH_MISMATCH,
    }
