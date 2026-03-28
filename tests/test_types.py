from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agent_slides.errors import AgentSlidesError, INVALID_SLIDE
from agent_slides.model.types import ComputedDeck, ComputedNode, Counters, Deck, Node, Slide


def build_deck() -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=3,
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Hello world",
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=54.0,
                        width=576.0,
                        height=80.0,
                        font_size_pt=28.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color="#FFFFFF",
                        font_bold=True,
                        revision=3,
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def test_models_are_importable_and_constructible() -> None:
    deck = build_deck()

    assert deck.deck_id == "deck-1"
    assert deck.slides[0].nodes[0].content == "Hello world"


def test_deck_json_round_trip_uses_counters_alias() -> None:
    deck = build_deck()

    payload = deck.model_dump_json()
    decoded = json.loads(payload)

    assert "_counters" in decoded
    assert "counters" not in decoded

    restored = Deck.model_validate_json(payload)

    assert json.loads(restored.model_dump_json()) == decoded


def test_next_ids_increment_counters() -> None:
    deck = Deck(deck_id="deck-1")

    assert deck.next_slide_id() == "s-1"
    assert deck.next_slide_id() == "s-2"
    assert deck.next_node_id() == "n-1"
    assert deck.counters.slides == 2
    assert deck.counters.nodes == 1


def test_get_slide_supports_index_and_id() -> None:
    deck = build_deck()

    assert deck.get_slide(0).slide_id == "s-1"
    assert deck.get_slide("s-1").layout == "title"


def test_get_slide_raises_invalid_slide_error() -> None:
    deck = build_deck()

    with pytest.raises(AgentSlidesError) as exc_info:
        deck.get_slide(99)

    assert exc_info.value.code == INVALID_SLIDE


def test_text_only_nodes_reject_image_type() -> None:
    with pytest.raises(ValidationError):
        Node(node_id="n-2", type="image")


def test_bump_revision_increments_by_one() -> None:
    deck = Deck(deck_id="deck-1", revision=10)

    deck.bump_revision()

    assert deck.revision == 11


def test_computed_node_includes_resolved_style_fields() -> None:
    computed = ComputedNode(
        x=0.0,
        y=0.0,
        width=720.0,
        height=540.0,
        font_size_pt=18.0,
        font_family="IBM Plex Sans",
        color="#111111",
        bg_color="#FAFAFA",
        font_bold=False,
        revision=1,
    )

    assert computed.font_family == "IBM Plex Sans"
    assert computed.color == "#111111"
    assert computed.bg_color == "#FAFAFA"
    assert computed.font_bold is False


def test_computed_deck_round_trip_applies_only_matching_revision() -> None:
    deck = build_deck()
    computed = ComputedDeck.from_deck(deck)

    deck.slides[0].computed = {}
    computed.apply_to_deck(deck)

    assert deck.slides[0].computed["n-1"].font_size_pt == 28.0

    deck.bump_revision()
    computed.apply_to_deck(deck)

    assert deck.slides[0].computed == {}
