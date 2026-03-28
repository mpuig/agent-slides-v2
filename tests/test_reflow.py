from __future__ import annotations

from pathlib import Path

import pytest

from agent_slides.engine.reflow import reflow_slide
from agent_slides.model import Node, Slide, get_layout
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
            Node(node_id="n-2", slot_binding="body", type="chart", content='{"series":[1,2,3]}'),
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
