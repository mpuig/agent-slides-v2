from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError
from agent_slides.errors import (
    AgentSlidesError,
    CHART_DATA_ERROR,
    INVALID_CHART_TYPE,
    INVALID_SLIDE,
)
from agent_slides.model.types import (
    ChartSpec,
    ComputedDeck,
    ComputedNode,
    Counters,
    Deck,
    Node,
    NodeContent,
    Slide,
    TextBlock,
)


def build_chart_node() -> Node:
    return Node(
        node_id="n-chart-1",
        type="chart",
        chart_spec=ChartSpec(
            chart_type="bar",
            title="Quarterly revenue",
            categories=["Q1", "Q2"],
            series=[{"name": "Revenue", "values": [1.0, 2.0]}],
        ),
    )


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
    assert deck.slides[0].nodes[0].content == NodeContent(
        blocks=[TextBlock(type="paragraph", text="Hello world")]
    )


def test_deck_json_round_trip_uses_counters_alias() -> None:
    deck = build_deck()

    payload = deck.model_dump_json()
    decoded = json.loads(payload)

    assert "_counters" in decoded
    assert "counters" not in decoded

    restored = Deck.model_validate_json(payload)

    assert json.loads(restored.model_dump_json()) == decoded


def test_legacy_string_content_is_coerced_to_structured_paragraphs() -> None:
    node = Node(node_id="n-1", type="text", content="Hello world")

    assert node.content == NodeContent(blocks=[TextBlock(type="paragraph", text="Hello world")])


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


def test_image_node_with_relative_path_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    monkeypatch.chdir(tmp_path)

    node = Node(node_id="n-2", type="image", image_path="photo.png")

    assert node.content == "photo.png"
    assert node.image_path == str(image_path.resolve())


def test_image_nodes_require_image_path() -> None:
    with pytest.raises(ValidationError, match="image_path"):
        Node(node_id="n-2", type="image")


def test_image_nodes_validate_file_existence_and_supported_format(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="does not exist"):
        Node(node_id="n-2", type="image", image_path=str(tmp_path / "missing.png"))

    unsupported_image = tmp_path / "logo.gif"
    unsupported_image.write_bytes(b"GIF89a")

    with pytest.raises(ValidationError, match="supported image format"):
        Node(node_id="n-3", type="image", image_path=str(unsupported_image))


def test_large_image_nodes_emit_warning(tmp_path: Path) -> None:
    large_image = tmp_path / "large.png"
    large_image.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"0" * ((5 * 1024 * 1024) + 1)))

    with pytest.warns(UserWarning, match="larger than 5MB"):
        Node(node_id="n-2", type="image", image_path=str(large_image))


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
        content_type="image",
    )

    assert computed.font_family == "IBM Plex Sans"
    assert computed.color == "#111111"
    assert computed.bg_color == "#FAFAFA"
    assert computed.font_bold is False
    assert computed.content_type == "image"
    assert computed.image_fit == "contain"


def test_image_nodes_round_trip_through_json_serialization(tmp_path: Path) -> None:
    image_path = tmp_path / "diagram.svg"
    image_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")

    node = Node(node_id="n-9", type="image", image_path=str(image_path))
    restored = Node.model_validate_json(node.model_dump_json())

    assert restored == node
    assert json.loads(node.model_dump_json())["image_path"] == str(image_path.resolve())


def test_computed_deck_round_trip_applies_only_matching_revision() -> None:
    deck = build_deck()
    computed = ComputedDeck.from_deck(deck)

    deck.slides[0].computed = {}
    computed.apply_to_deck(deck)

    assert deck.slides[0].computed["n-1"].font_size_pt == 28.0

    deck.bump_revision()
    computed.apply_to_deck(deck)

    assert deck.slides[0].computed == {}


def test_chart_nodes_accept_chart_type_and_round_trip_json() -> None:
    node = build_chart_node()
    restored = Node.model_validate_json(node.model_dump_json())

    assert restored == node
    assert restored.type == "chart"
    assert restored.chart_spec is not None
    assert restored.chart_spec.chart_type == "bar"
    assert json.loads(node.model_dump_json())["chart_spec"]["series"][0]["values"] == [1.0, 2.0]


def test_chart_nodes_require_chart_spec() -> None:
    with pytest.raises(ValidationError, match="chart_spec"):
        Node(node_id="n-chart-2", type="chart")


def test_chart_spec_rejects_unknown_chart_type() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(chart_type="radar")

    assert exc_info.value.errors()[0]["type"] == INVALID_CHART_TYPE


def test_category_charts_require_categories_and_series_data() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(chart_type="bar", categories=["Q1", "Q2"], series=[{"name": "Revenue", "values": [1.0]}])

    assert exc_info.value.errors()[0]["type"] == CHART_DATA_ERROR


def test_scatter_charts_require_scatter_series() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(chart_type="scatter")

    assert exc_info.value.errors()[0]["type"] == CHART_DATA_ERROR


def test_pie_charts_require_a_single_series() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(
            chart_type="pie",
            categories=["A", "B"],
            series=[
                {"name": "North", "values": [1.0, 2.0]},
                {"name": "South", "values": [3.0, 4.0]},
            ],
        )

    assert exc_info.value.errors()[0]["type"] == CHART_DATA_ERROR


def test_pie_charts_warn_on_negative_values() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = ChartSpec(
            chart_type="pie",
            categories=["A", "B"],
            series=[{"name": "Revenue", "values": [1.0, -2.0]}],
        )

    assert spec.chart_type == "pie"
    assert any("negative values" in str(warning.message) for warning in caught)


def test_chart_specs_warn_when_more_than_ten_series() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = ChartSpec(
            chart_type="line",
            categories=["Jan", "Feb"],
            series=[
                {"name": f"Series {index}", "values": [float(index), float(index + 1)]}
                for index in range(11)
            ],
        )

    assert spec.chart_type == "line"
    assert any("more than 10 series" in str(warning.message) for warning in caught)
