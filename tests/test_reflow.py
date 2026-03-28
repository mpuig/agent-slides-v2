from __future__ import annotations

from math import isclose

from agent_slides.engine.reflow import rebind_slots, reflow_deck, reflow_slide
from agent_slides.model.layouts import get_layout
from agent_slides.model.themes import load_theme
from agent_slides.model.types import Deck, Node, Slide


def _assert_close(actual: float, expected: float) -> None:
    assert isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9)


def test_reflow_slide_computes_title_layout_geometry_and_styles() -> None:
    slide = Slide(
        slide_id="s-1",
        layout="title",
        nodes=[
            Node(node_id="n-1", type="text", slot_binding="title", content="Quarterly update"),
            Node(node_id="n-2", type="text", slot_binding="subtitle", content="Momentum is compounding"),
            Node(node_id="n-3", type="text", content="Unbound note"),
        ],
    )

    reflow_slide(slide, get_layout("title"), load_theme("default"))

    assert set(slide.computed) == {"n-1", "n-2"}

    title = slide.computed["n-1"]
    subtitle = slide.computed["n-2"]

    _assert_close(title.x, 60.0)
    _assert_close(title.y, 60.0)
    _assert_close(title.width, 600.0)
    _assert_close(title.height, 168.0)
    _assert_close(title.font_size_pt, 32.0)
    assert title.font_family == "Calibri"
    assert title.color == "#1a1a2e"
    assert title.bg_color == "#ffffff"
    assert title.font_bold is True
    assert title.revision == 0

    _assert_close(subtitle.x, 60.0)
    _assert_close(subtitle.y, 248.0)
    _assert_close(subtitle.width, 600.0)
    _assert_close(subtitle.height, 252.0)
    _assert_close(subtitle.font_size_pt, 18.0)
    assert subtitle.font_family == "Calibri"
    assert subtitle.color == "#333333"
    assert subtitle.font_bold is False


def test_reflow_slide_computes_two_column_geometry_with_spanning_title() -> None:
    slide = Slide(
        slide_id="s-1",
        layout="two_col",
        nodes=[
            Node(node_id="n-1", type="text", slot_binding="title", content="Decision"),
            Node(node_id="n-2", type="text", slot_binding="col1", content="Left"),
            Node(node_id="n-3", type="text", slot_binding="col2", content="Right"),
        ],
    )

    reflow_slide(slide, get_layout("two_col"), load_theme("default"))

    title = slide.computed["n-1"]
    col1 = slide.computed["n-2"]
    col2 = slide.computed["n-3"]

    _assert_close(title.x, 60.0)
    _assert_close(title.y, 60.0)
    _assert_close(title.width, 620.0)
    _assert_close(title.height, 50.4)

    _assert_close(col1.x, 60.0)
    _assert_close(col1.y, 130.4)
    _assert_close(col1.width, 300.0)
    _assert_close(col1.height, 369.6)

    _assert_close(col2.x, 380.0)
    _assert_close(col2.y, 130.4)
    _assert_close(col2.width, 300.0)
    _assert_close(col2.height, 369.6)


def test_reflow_deck_processes_all_slides_and_uses_deck_revision() -> None:
    deck = Deck(
        deck_id="deck-1",
        revision=7,
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", type="text", slot_binding="title", content="Title slide")],
            ),
            Slide(
                slide_id="s-2",
                layout="quote",
                nodes=[
                    Node(node_id="n-2", type="text", slot_binding="quote", content="Quote"),
                    Node(node_id="n-3", type="text", slot_binding="attribution", content="Source"),
                ],
            ),
        ],
    )

    reflow_deck(deck)

    assert deck.slides[0].computed["n-1"].revision == 7
    assert deck.slides[1].computed["n-2"].revision == 7
    assert deck.slides[1].computed["n-3"].revision == 7
    _assert_close(deck.slides[1].computed["n-2"].font_size_pt, 28.0)
    _assert_close(deck.slides[1].computed["n-3"].font_size_pt, 16.0)


def test_rebind_slots_keeps_matching_bindings_and_unbinds_missing_slots() -> None:
    slide = Slide(
        slide_id="s-1",
        layout="three_col",
        nodes=[
            Node(node_id="n-1", type="text", slot_binding="title"),
            Node(node_id="n-2", type="text", slot_binding="col1"),
            Node(node_id="n-3", type="text", slot_binding="col2"),
            Node(node_id="n-4", type="text", slot_binding="col3"),
            Node(node_id="n-5", type="text"),
        ],
    )

    unbound = rebind_slots(slide, get_layout("two_col"))

    assert unbound == ["n-4"]
    assert slide.layout == "two_col"
    assert slide.nodes[0].slot_binding == "title"
    assert slide.nodes[1].slot_binding == "col1"
    assert slide.nodes[2].slot_binding == "col2"
    assert slide.nodes[3].slot_binding is None
    assert slide.nodes[4].slot_binding is None


def test_rebind_slots_to_same_layout_is_a_no_op() -> None:
    slide = Slide(
        slide_id="s-1",
        layout="two_col",
        nodes=[
            Node(node_id="n-1", type="text", slot_binding="title"),
            Node(node_id="n-2", type="text", slot_binding="col1"),
            Node(node_id="n-3", type="text", slot_binding="col2"),
        ],
    )

    unbound = rebind_slots(slide, get_layout("two_col"))

    assert unbound == []
    assert slide.layout == "two_col"
    assert [node.slot_binding for node in slide.nodes] == ["title", "col1", "col2"]
