from __future__ import annotations

from agent_slides.engine.reflow import reflow_deck
from agent_slides.model.types import Counters, Deck, Node, Slide


def test_reflow_positions_image_nodes_on_the_same_grid_as_text_nodes() -> None:
    text_deck = Deck(
        deck_id="deck-text",
        theme="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="text",
                        content="Hello",
                    )
                ],
                computed={},
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )
    image_deck = Deck(
        deck_id="deck-image",
        theme="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="image",
                        image_path="photo.png",
                        image_fit="cover",
                    )
                ],
                computed={},
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )

    reflow_deck(text_deck)
    reflow_deck(image_deck)

    text_node = text_deck.slides[0].computed["n-1"]
    image_node = image_deck.slides[0].computed["n-1"]

    assert (image_node.x, image_node.y, image_node.width, image_node.height) == (
        text_node.x,
        text_node.y,
        text_node.width,
        text_node.height,
    )
    assert image_node.image_fit == "cover"
    assert image_node.font_size_pt == 0.0
    assert image_node.text_overflow is False
