from __future__ import annotations

from pathlib import Path

import pytest

import agent_slides.engine.reflow as reflow_module
from agent_slides.engine.reflow import reflow_deck, reflow_slide
from agent_slides.model import Counters, Deck, LayoutDef, Node, Slide, SlotDef, TextBlock, TextFitting, get_layout
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.types import GridDef, NodeContent
from agent_slides.model.themes import load_theme


def make_image(tmp_path: Path) -> str:
    image_path = tmp_path / "placeholder.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    return str(image_path)


def test_reflow_chart_nodes_use_grid_geometry_without_text_fitting() -> None:
    slide = Slide(
        slide_id="s-chart",
        layout="title_content",
        nodes=[
            Node(node_id="n-1", slot_binding="heading", type="text", content="KPI summary"),
            Node(
                node_id="n-2",
                slot_binding="body",
                type="chart",
                chart_spec={
                    "chart_type": "bar",
                    "categories": ["Q1", "Q2", "Q3"],
                    "series": [{"name": "Revenue", "values": [1.0, 2.0, 3.0]}],
                },
            ),
        ],
    )

    reflow_slide(slide, get_layout("title_content"), load_theme("default"))

    heading = slide.computed["n-1"]
    chart = slide.computed["n-2"]

    assert heading.content_type == "text"
    assert heading.font_size_pt > 0.0

    assert chart.x == pytest.approx(60.0)
    assert chart.y == pytest.approx(130.4)
    assert chart.width == pytest.approx(600.0)
    assert chart.height == pytest.approx(369.6)
    assert chart.font_size_pt == 0.0
    assert chart.text_overflow is False
    assert chart.content_type == "chart"


def test_reflow_scatter_chart_nodes_keep_chart_content_type() -> None:
    slide = Slide(
        slide_id="s-scatter",
        layout="title_content",
        nodes=[
            Node(node_id="n-1", slot_binding="heading", type="text", content="Correlation"),
            Node(
                node_id="n-2",
                slot_binding="body",
                type="chart",
                chart_spec={
                    "chart_type": "scatter",
                    "scatter_series": [
                        {
                            "name": "Observations",
                            "points": [{"x": 1.0, "y": 2.0}, {"x": 2.5, "y": 3.5}],
                        }
                    ],
                },
            ),
        ],
    )

    reflow_slide(slide, get_layout("title_content"), load_theme("default"))

    chart = slide.computed["n-2"]

    assert chart.content_type == "chart"
    assert chart.font_size_pt == 0.0


def test_reflow_table_nodes_use_grid_geometry_without_text_fitting() -> None:
    slide = Slide(
        slide_id="s-table",
        layout="title_content",
        nodes=[
            Node(node_id="n-1", slot_binding="heading", type="text", content="Quarterly summary"),
            Node(
                node_id="n-2",
                slot_binding="body",
                type="table",
                table_spec={
                    "headers": ["Metric", "Q1", "Q2"],
                    "rows": [
                        ["Revenue", "$100K", "$150K"],
                        ["Users", "1000", "1500"],
                    ],
                },
            ),
        ],
    )

    reflow_slide(slide, get_layout("title_content"), load_theme("default"))

    table = slide.computed["n-2"]

    assert table.x == pytest.approx(60.0)
    assert table.y == pytest.approx(130.4)
    assert table.width == pytest.approx(600.0)
    assert table.height == pytest.approx(369.6)
    assert table.font_size_pt == 0.0
    assert table.text_overflow is False
    assert table.content_type == "table"


def test_reflow_image_nodes_still_skip_text_fitting(tmp_path: Path) -> None:
    image_path = make_image(tmp_path)
    slide = Slide(
        slide_id="s-image",
        layout="gallery",
        nodes=[
            Node(node_id="n-1", slot_binding="heading", type="text", content="Snapshots"),
            Node(
                node_id="n-2",
                slot_binding="img1",
                type="image",
                image_path=image_path,
            ),
        ],
    )

    reflow_slide(slide, get_layout("gallery"), load_theme("default"))

    image = slide.computed["n-2"]

    assert image.font_size_pt == 0.0
    assert image.content_type == "image"
    assert image.text_overflow is False


def test_reflow_deck_normalizes_font_sizes_by_role(monkeypatch: pytest.MonkeyPatch) -> None:
    deck = Deck(
        deck_id="deck-normalized",
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Short heading"),
                    Node(node_id="n-2", slot_binding="body", type="text", content="Short body"),
                ],
            ),
            Slide(
                slide_id="s-2",
                layout="title_content",
                nodes=[
                    Node(node_id="n-3", slot_binding="heading", type="text", content="Long heading"),
                    Node(node_id="n-4", slot_binding="body", type="text", content="Long body"),
                ],
            ),
        ],
        counters=Counters(slides=2, nodes=4),
    )

    def fake_fit_text(*, text, width, height, default_size, min_size, role, font_family=None, ladder=None, use_precise=False):
        assert font_family == "Calibri"
        if ladder == [24.0]:
            return (24.0, False)
        if role == "heading":
            return (32.0, False) if text.to_plain_text() == "Short heading" else (24.0, False)
        return (18.0, False)

    monkeypatch.setattr(reflow_module, "fit_text", fake_fit_text)

    reflow_deck(deck)

    assert deck.slides[0].computed["n-1"].font_size_pt == 24.0
    assert deck.slides[1].computed["n-3"].font_size_pt == 24.0
    assert deck.slides[0].computed["n-2"].font_size_pt == 18.0


def test_reflow_composes_text_blocks_with_padding_spacing_and_per_block_sizes() -> None:
    slide = Slide(
        slide_id="s-text",
        layout="title_content",
        nodes=[
            Node(
                node_id="n-1",
                slot_binding="body",
                type="text",
                content=NodeContent(
                    blocks=[
                        TextBlock(type="heading", text="Overview"),
                        TextBlock(type="bullet", text="First point"),
                        TextBlock(type="bullet", text="Second point"),
                    ]
                ),
            )
        ],
    )

    reflow_slide(slide, get_layout("title_content"), load_theme("default"), load_design_rules("default"))

    computed = slide.computed["n-1"]

    assert computed.font_size_pt == 18.0
    assert len(computed.block_positions) == 3
    assert computed.block_positions[0].x == pytest.approx(68.0)
    assert computed.block_positions[0].y == pytest.approx(138.4)
    assert computed.block_positions[0].font_size_pt == 32.0
    assert computed.block_positions[1].font_size_pt == 18.0
    assert computed.block_positions[1].y == pytest.approx(
        computed.block_positions[0].y + computed.block_positions[0].height + 10.0
    )
    assert computed.block_positions[2].y == pytest.approx(
        computed.block_positions[1].y + computed.block_positions[1].height + 4.0
    )


def test_reflow_honors_vertical_alignment_and_peer_baseline_alignment() -> None:
    layout = LayoutDef(
        name="peer_alignment",
        slots={
            "col1": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                x=40.0,
                y=60.0,
                width=220.0,
                height=180.0,
                vertical_align="middle",
                peer_group="columns",
            ),
            "col2": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                x=300.0,
                y=60.0,
                width=220.0,
                height=100.0,
                vertical_align="middle",
                peer_group="columns",
            ),
            "footer": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                x=40.0,
                y=280.0,
                width=220.0,
                height=100.0,
                vertical_align="bottom",
            ),
        },
        grid=GridDef(columns=1, rows=1, row_heights=[1.0], col_widths=[1.0], margin=0.0, gutter=0.0),
        text_fitting={
            "heading": TextFitting(default_size=32.0, min_size=24.0),
            "body": TextFitting(default_size=18.0, min_size=10.0),
        },
    )
    slide = Slide(
        slide_id="s-peer",
        layout="peer_alignment",
        nodes=[
            Node(node_id="n-1", slot_binding="col1", type="text", content="Left column"),
            Node(node_id="n-2", slot_binding="col2", type="text", content="Right column"),
            Node(node_id="n-3", slot_binding="footer", type="text", content="Bottom aligned"),
        ],
    )

    reflow_slide(slide, layout, load_theme("default"), load_design_rules("default"))

    left = slide.computed["n-1"].block_positions[0]
    right = slide.computed["n-2"].block_positions[0]
    footer = slide.computed["n-3"].block_positions[0]

    assert left.y == pytest.approx(right.y)
    assert footer.y == pytest.approx(350.4)
