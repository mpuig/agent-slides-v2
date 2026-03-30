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
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.types import (
    BlockPosition,
    ChartSpec,
    ChartStyle,
    ComputedDeck,
    ComputedNode,
    ComputedPatternElement,
    Counters,
    Deck,
    Node,
    NodeContent,
    PatternSpec,
    Slide,
    SlotDef,
    TableSpec,
    TextBlock,
    TextFitting,
    TextRun,
    apply_inline_color_suffixes,
    parse_inline_markdown_runs,
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


def build_table_node() -> Node:
    return Node(
        node_id="n-table-1",
        type="table",
        table_spec=TableSpec(
            headers=["Metric", "Q1", "Q2"],
            rows=[
                ["Revenue", "$100K", "$150K"],
                ["Users", "1000", "1500"],
            ],
        ),
    )


def build_pattern_node() -> Node:
    return Node(
        node_id="n-pattern-1",
        slot_binding="body",
        type="pattern",
        pattern_spec=PatternSpec(
            pattern_type="kpi-row",
            data=[
                {"value": "87%", "label": "Adoption"},
                {"value": "3.2x", "label": "ROI"},
            ],
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

    assert node.content == NodeContent(
        blocks=[TextBlock(type="paragraph", text="Hello world")]
    )


def test_node_content_from_text_converts_mixed_bullet_lines_to_blocks() -> None:
    content = NodeContent.from_text("Key points:\n- First item\n* Second item")

    assert content == NodeContent(
        blocks=[
            TextBlock(type="paragraph", text="Key points:"),
            TextBlock(type="bullet", text="First item"),
            TextBlock(type="bullet", text="Second item"),
        ]
    )


def test_node_content_from_text_keeps_empty_single_line_and_plain_multiline_text_unchanged() -> (
    None
):
    assert NodeContent.from_text("") == NodeContent(blocks=[])
    assert NodeContent.from_text("Hello world") == NodeContent(
        blocks=[TextBlock(type="paragraph", text="Hello world")]
    )
    assert NodeContent.from_text("Line one\nLine two") == NodeContent(
        blocks=[TextBlock(type="paragraph", text="Line one\nLine two")]
    )


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


def test_image_nodes_require_image_path() -> None:
    with pytest.raises(ValidationError):
        Node(node_id="n-2", type="image")


def test_image_nodes_cannot_define_text_content() -> None:
    with pytest.raises(ValidationError):
        Node(
            node_id="n-2",
            type="image",
            image_path="photo.png",
            content="caption",
        )


def test_chart_nodes_do_not_allow_image_path() -> None:
    with pytest.raises(ValidationError, match="image_path"):
        Node(
            node_id="n-chart",
            type="chart",
            image_path="chart.png",
            chart_spec={
                "chart_type": "bar",
                "categories": ["Q1"],
                "series": [{"name": "Revenue", "values": [1.0]}],
            },
        )


def test_chart_nodes_default_content_to_empty_structured_content() -> None:
    node = build_chart_node()

    assert node.type == "chart"
    assert node.image_path is None
    assert node.content == NodeContent()


def test_image_nodes_are_constructible() -> None:
    node = Node(node_id="n-2", type="image", image_path="photo.png", image_fit="cover")

    assert node.image_path == "photo.png"
    assert node.image_fit == "cover"


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
        block_positions=[
            BlockPosition(
                block_index=0,
                x=8.0,
                y=8.0,
                width=200.0,
                height=28.0,
                font_size_pt=18.0,
            )
        ],
    )

    assert computed.font_family == "IBM Plex Sans"
    assert computed.color == "#111111"
    assert computed.bg_color == "#FAFAFA"
    assert computed.font_bold is False
    assert computed.content_type == "image"
    assert computed.image_fit == "contain"
    assert computed.block_positions[0].font_size_pt == 18.0


def test_computed_node_accepts_chart_content_type() -> None:
    computed = ComputedNode(
        x=0.0,
        y=0.0,
        width=320.0,
        height=180.0,
        font_size_pt=0.0,
        font_family="IBM Plex Sans",
        color="#111111",
        revision=1,
        content_type="chart",
    )

    assert computed.content_type == "chart"


def test_slot_def_defaults_include_padding_and_top_alignment() -> None:
    slot = SlotDef(grid_row=1, grid_col=1, role="body")

    assert slot.padding == 8.0
    assert slot.vertical_align == "top"
    assert slot.peer_group is None


def test_computed_node_accepts_table_content_type() -> None:
    computed = ComputedNode(
        x=0.0,
        y=0.0,
        width=320.0,
        height=180.0,
        font_size_pt=0.0,
        font_family="IBM Plex Sans",
        color="#111111",
        revision=1,
        content_type="table",
    )

    assert computed.content_type == "table"
    assert computed.font_size_pt == 0.0


def test_computed_node_accepts_pattern_content_type_and_elements() -> None:
    computed = ComputedNode(
        x=0.0,
        y=0.0,
        width=320.0,
        height=180.0,
        font_size_pt=0.0,
        font_family="IBM Plex Sans",
        color="#111111",
        revision=1,
        content_type="pattern",
        pattern_elements=[
            ComputedPatternElement(
                kind="shape",
                shape_type="rounded_rectangle",
                x=0.0,
                y=0.0,
                width=120.0,
                height=80.0,
                fill_color="#F2F2F2",
            ),
            ComputedPatternElement(
                kind="text",
                text="Adoption",
                x=10.0,
                y=12.0,
                width=100.0,
                height=24.0,
                font_size_pt=14.0,
                font_family="IBM Plex Sans",
                color="#111111",
            ),
        ],
    )

    assert computed.content_type == "pattern"
    assert len(computed.pattern_elements) == 2


def test_image_nodes_round_trip_through_json_serialization(tmp_path: Path) -> None:
    image_path = tmp_path / "diagram.svg"
    image_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8"
    )

    node = Node(node_id="n-9", type="image", image_path=str(image_path))
    restored = Node.model_validate_json(node.model_dump_json())

    assert restored == node
    assert json.loads(node.model_dump_json())["image_path"] == str(image_path.resolve())


def test_computed_node_defaults_support_image_nodes() -> None:
    computed = ComputedNode(
        x=10.0,
        y=20.0,
        width=200.0,
        height=100.0,
        revision=1,
        image_fit="stretch",
    )

    assert computed.image_fit == "stretch"
    assert computed.font_size_pt == 0.0


def test_computed_node_supports_layout_fallback_metadata() -> None:
    computed = ComputedNode(
        x=10.0,
        y=20.0,
        width=200.0,
        height=100.0,
        revision=1,
        layout_used="image_right",
        layout_fallback_reason="Forced primary failure",
        layout_overflow_reason="text overflow in body",
    )

    assert computed.layout_used == "image_right"
    assert computed.layout_fallback_reason == "Forced primary failure"
    assert computed.layout_overflow_reason == "text overflow in body"


def test_text_fitting_supports_custom_ladders() -> None:
    fitting = TextFitting(default_size=20, min_size=10, ladder=[20, 16, 12])

    assert fitting.ladder == [20, 16, 12]


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
    assert json.loads(node.model_dump_json())["chart_spec"]["series"][0]["values"] == [
        1.0,
        2.0,
    ]


def test_table_nodes_default_content_to_empty_structured_content() -> None:
    node = build_table_node()

    assert node.type == "table"
    assert node.content == NodeContent()
    assert node.table_spec is not None


def test_table_nodes_accept_table_spec_and_round_trip_json() -> None:
    node = build_table_node()
    restored = Node.model_validate_json(node.model_dump_json())

    assert restored == node
    assert restored.type == "table"
    assert restored.table_spec is not None
    assert restored.table_spec.headers == ["Metric", "Q1", "Q2"]


def test_pattern_nodes_accept_pattern_spec_and_round_trip_json() -> None:
    node = build_pattern_node()
    restored = Node.model_validate_json(node.model_dump_json())

    assert restored == node
    assert restored.type == "pattern"
    assert restored.pattern_spec is not None
    assert restored.pattern_spec.pattern_type == "kpi-row"


def test_table_nodes_require_table_spec() -> None:
    with pytest.raises(ValidationError, match="table_spec"):
        Node(node_id="n-table-2", type="table")


def test_pattern_nodes_require_pattern_spec() -> None:
    with pytest.raises(ValidationError, match="pattern_spec"):
        Node(node_id="n-pattern-2", slot_binding="body", type="pattern")


def test_table_spec_auto_detects_numeric_columns_and_widths() -> None:
    spec = TableSpec(
        headers=["Metric", "Q1", "Q2"],
        rows=[
            ["Revenue", "$100K", "$150K"],
            ["Users", "1000", "1500"],
        ],
    )

    assert spec.infer_numeric_columns() == [False, True, True]
    assert spec.resolved_col_align() == ["left", "right", "right"]
    assert spec.resolved_col_widths()[0] > spec.resolved_col_widths()[1]


def test_table_spec_rejects_row_length_mismatch() -> None:
    with pytest.raises(ValidationError, match="rows\\[0\\] has 1 values for 2 headers"):
        TableSpec(headers=["Metric", "Q1"], rows=[["Revenue"]])


def test_chart_nodes_require_chart_spec() -> None:
    with pytest.raises(ValidationError, match="chart_spec"):
        Node(node_id="n-chart-2", type="chart")


def test_chart_spec_rejects_unknown_chart_type() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(chart_type="radar")

    assert exc_info.value.errors()[0]["type"] == INVALID_CHART_TYPE


def test_category_charts_require_categories_and_series_data() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChartSpec(
            chart_type="bar",
            categories=["Q1", "Q2"],
            series=[{"name": "Revenue", "values": [1.0]}],
        )

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


def test_chart_style_validates_series_colors() -> None:
    style = ChartStyle(series_colors=["#FF0000", "00FF00"])

    assert style.series_colors == ["#FF0000", "00FF00"]

    with pytest.raises(
        ValidationError, match="series_colors entries must use #RRGGBB or RRGGBB format"
    ):
        ChartStyle(series_colors=["bad-color"])


def test_parse_inline_markdown_color_suffixes_use_design_rule_aliases() -> None:
    aliases = load_design_rules("default").conditional_formatting.color_aliases
    runs = parse_inline_markdown_runs("Revenue: **+23%**{green} vs target **-5%**{red}")

    assert runs is not None
    assert apply_inline_color_suffixes(runs, color_aliases=aliases) == [
        TextRun(text="Revenue: "),
        TextRun(text="+23%", bold=True, color="#1B8A2D"),
        TextRun(text=" vs target "),
        TextRun(text="-5%", bold=True, color="#D32F2F"),
    ]


def test_chart_style_accepts_conditional_point_color_settings() -> None:
    style = ChartStyle(
        color_by_value=True,
        highlight_index=1,
        highlight_color="#C98E48",
        muted_color="CFC8BD",
    )

    assert style.color_by_value is True
    assert style.highlight_index == 1
    assert style.highlight_color == "#C98E48"
    assert style.muted_color == "#CFC8BD"

    with pytest.raises(ValidationError, match="highlight_index"):
        ChartStyle(highlight_index=-1)


def test_design_rules_default_profile_exposes_conditional_formatting() -> None:
    rules = load_design_rules("default")

    assert rules.conditional_formatting.color_aliases["green"] == "#1B8A2D"
    assert any(
        rule.pattern == "positive_number"
        for rule in rules.conditional_formatting.text_rules
    )
    assert rules.conditional_formatting.table.statuses["in progress"].fill == "#FFF1C7"
