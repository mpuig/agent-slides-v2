from __future__ import annotations

from pathlib import Path

import pytest

from agent_slides.engine.reflow import rebind_slots, reflow_slide
from agent_slides.model import Deck, Node, Slide, get_layout, list_layouts
from agent_slides.model.themes import load_theme


def make_image(tmp_path: Path, name: str) -> Path:
    image_path = tmp_path / name
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    return image_path


@pytest.mark.parametrize(
    ("layout_name", "expected_roles"),
    [
        ("image_left", {"image": "image", "heading": "heading", "body": "body"}),
        ("image_right", {"heading": "heading", "body": "body", "image": "image"}),
        ("hero_image", {"image": "image", "heading": "heading", "subheading": "body"}),
        (
            "gallery",
            {
                "heading": "heading",
                "img1": "image",
                "img2": "image",
                "img3": "image",
                "img4": "image",
            },
        ),
    ],
)
def test_image_capable_layouts_are_registered_with_expected_slots(
    layout_name: str,
    expected_roles: dict[str, str],
) -> None:
    assert layout_name in list_layouts()

    layout = get_layout(layout_name)

    assert {slot_name: slot.role for slot_name, slot in layout.slots.items()} == expected_roles


def test_reflow_image_left_computes_mixed_image_and_text_frames(tmp_path: Path) -> None:
    image_path = make_image(tmp_path, "example.png")
    slide = Slide(
        slide_id="s-1",
        layout="image_left",
        nodes=[
            Node(node_id="n-1", slot_binding="image", type="image", image_path=str(image_path)),
            Node(node_id="n-2", slot_binding="heading", type="text", content="Quarterly growth"),
            Node(node_id="n-3", slot_binding="body", type="text", content="Revenue expanded across all regions."),
        ],
    )

    reflow_slide(slide, get_layout("image_left"), load_theme("default"))

    image = slide.computed["n-1"]
    heading = slide.computed["n-2"]
    body = slide.computed["n-3"]

    assert image.x == pytest.approx(60.0)
    assert image.y == pytest.approx(60.0)
    assert image.width == pytest.approx(300.0)
    assert image.height == pytest.approx(440.0)
    assert image.font_size_pt == 0.0
    assert image.text_overflow is False

    assert heading.x == pytest.approx(380.0)
    assert heading.y == pytest.approx(60.0)
    assert heading.width == pytest.approx(300.0)
    assert heading.height == pytest.approx(117.6)
    assert body.x == pytest.approx(380.0)
    assert body.y == pytest.approx(197.6)
    assert body.width == pytest.approx(300.0)
    assert body.height == pytest.approx(302.4)


def test_reflow_hero_image_full_bleed_image_and_overlay_text(tmp_path: Path) -> None:
    image_path = make_image(tmp_path, "hero.png")
    slide = Slide(
        slide_id="s-hero",
        layout="hero_image",
        nodes=[
            Node(node_id="n-1", slot_binding="image", type="image", image_path=str(image_path)),
            Node(node_id="n-2", slot_binding="heading", type="text", content="Launch day"),
            Node(node_id="n-3", slot_binding="subheading", type="text", content="A single story over a full-bleed visual."),
        ],
    )

    reflow_slide(slide, get_layout("hero_image"), load_theme("default"))

    image = slide.computed["n-1"]
    heading = slide.computed["n-2"]
    subheading = slide.computed["n-3"]

    assert image.x == pytest.approx(0.0)
    assert image.y == pytest.approx(0.0)
    assert image.width == pytest.approx(720.0)
    assert image.height == pytest.approx(540.0)
    assert heading.bg_color == "#FFFFFF"
    assert heading.bg_transparency == pytest.approx(0.25)
    assert subheading.bg_color == "#FFFFFF"
    assert subheading.bg_transparency == pytest.approx(0.25)


def test_rebind_slots_creates_image_nodes_for_image_layouts() -> None:
    deck = Deck(deck_id="deck-1")
    slide = Slide(
        slide_id="s-1",
        layout="title_content",
        nodes=[
            Node(node_id=deck.next_node_id(), slot_binding="heading", type="text", content="Heading"),
            Node(node_id=deck.next_node_id(), slot_binding="body", type="text", content="Body"),
        ],
    )
    deck.slides.append(slide)

    unbound = rebind_slots(deck, slide, get_layout("gallery"))

    assert unbound == ["n-2"]
    assert [(node.slot_binding, node.type) for node in slide.nodes] == [
        ("heading", "text"),
        (None, "text"),
        ("img1", "image"),
        ("img2", "image"),
        ("img3", "image"),
        ("img4", "image"),
    ]
    assert all(node.style_overrides.get("placeholder") is True for node in slide.nodes[2:])


@pytest.mark.parametrize("layout_name", [name for name in list_layouts() if name != "blank"])
def test_builtin_layout_slots_include_semantic_metadata(layout_name: str) -> None:
    layout = get_layout(layout_name)

    assert all(slot.alignment_group is not None for slot in layout.slots.values())
    assert sorted(slot.reading_order for slot in layout.slots.values()) == list(range(len(layout.slots)))

    if layout_name == "two_col":
        assert layout.slots["heading"].alignment_group == "top"
        assert layout.slots["heading"].size_policy == "fit_content"
        assert layout.slots["col1"].peer_group == "columns"
        assert layout.slots["col1"].alignment_group == "content"
        assert layout.slots["col2"].peer_group == "columns"

    if layout_name == "gallery":
        assert layout.slots["img1"].peer_group == "gallery"
        assert layout.slots["img2"].alignment_group == "gallery_row_1"
        assert layout.slots["img4"].alignment_group == "gallery_row_2"
