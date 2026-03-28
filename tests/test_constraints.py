from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_slides.engine.constraints import Anchor, SlotConstraints, constraints_from_layout, solve, validate_constraints
from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.model import GridDef, LayoutDef, SlotDef, TemplateLayoutRegistry, TextFitting, list_layouts
from agent_slides.model.layouts import SLIDE_HEIGHT_PT, SLIDE_WIDTH_PT, get_layout
from agent_slides.model.themes import load_theme


def _write_manifest(path: Path) -> None:
    (path.parent / "template.pptx").write_bytes(b"pptx")
    path.write_text(
        json.dumps(
            {
                "name": "template",
                "source": "template.pptx",
                "source_hash": "abc123",
                "layouts": [
                    {
                        "slug": "photo_story",
                        "usable": True,
                        "slot_mapping": {
                            "heading": {
                                "role": "heading",
                                "bounds": {"x": 72.0, "y": 64.0, "width": 560.0, "height": 96.0},
                            },
                            "body": {
                                "role": "body",
                                "bounds": {"x": 72.0, "y": 180.0, "width": 560.0, "height": 220.0},
                            },
                        },
                    }
                ],
                "theme": {
                    "colors": {
                        "primary": "#101820",
                        "secondary": "#203040",
                        "accent": "#ff6600",
                        "background": "#faf7f2",
                        "text": "#1f1f1f",
                    },
                    "fonts": {"heading": "Aptos Display", "body": "Aptos"},
                    "spacing": {"base_unit": 12, "margin": 48, "gutter": 18},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_constraints_from_layout_supports_all_builtin_layouts() -> None:
    theme = load_theme("default")

    for layout_name in list_layouts():
        layout = get_layout(layout_name)
        constraints = constraints_from_layout(layout, theme)
        assert set(constraints) == set(layout.slots)


def test_constraints_from_layout_preserves_template_bounds(tmp_path: Path) -> None:
    manifest_path = tmp_path / "template.manifest.json"
    _write_manifest(manifest_path)
    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("photo_story")

    constraints = constraints_from_layout(layout, TemplateLayoutRegistry(str(manifest_path)).theme)

    heading = constraints["heading"]
    assert heading.left == Anchor(reference="slide", edge="left", offset=72.0)
    assert heading.top == Anchor(reference="slide", edge="top", offset=64.0)
    assert heading.right == Anchor(reference="slide", edge="right", offset=-88.0)
    assert heading.bottom == Anchor(reference="slide", edge="bottom", offset=-380.0)


def test_constraints_from_layout_reuses_vertical_alignment_group_bounds() -> None:
    layout = LayoutDef(
        name="aligned",
        slots={
            "left": SlotDef(
                grid_row=1,
                grid_col=1,
                role="body",
                x=40.0,
                y=80.0,
                width=200.0,
                height=140.0,
                alignment_group="body-row",
            ),
            "right": SlotDef(
                grid_row=1,
                grid_col=2,
                role="body",
                x=280.0,
                y=88.0,
                width=200.0,
                height=128.0,
                alignment_group="body-row",
            ),
        },
        grid=GridDef(columns=2, rows=1, row_heights=[1.0], col_widths=[0.5, 0.5], margin=0.0, gutter=0.0),
        text_fitting={"body": TextFitting(default_size=18.0, min_size=10.0)},
    )

    constraints = constraints_from_layout(layout, load_theme("default"))

    assert constraints["left"].top == constraints["right"].top
    assert constraints["left"].bottom == constraints["right"].bottom


def test_solve_supports_equal_share_fit_content_and_fill_remaining() -> None:
    constraints = {
        "heading": SlotConstraints(
            left=Anchor("slide", "left", 60.0),
            top=Anchor("slide", "top", 40.0),
            right=Anchor("slide", "right", -60.0),
            bottom=Anchor("slide", "top", 100.0),
            reading_order=0,
        ),
        "body": SlotConstraints(
            left=Anchor("slide", "left", 60.0),
            top=Anchor("heading", "bottom", 20.0),
            right=Anchor("slide", "right", -60.0),
            bottom=None,
            height_mode="fit_content",
            reading_order=1,
        ),
        "col1": SlotConstraints(
            left=Anchor("slide", "left", 60.0),
            top=Anchor("slide", "top", 260.0),
            right=Anchor("slide", "right", -60.0),
            bottom=Anchor("slide", "bottom", -60.0),
            width_mode="equal_share",
            reading_order=2,
            share_group="cols",
        ),
        "col2": SlotConstraints(
            left=Anchor("slide", "left", 60.0),
            top=Anchor("slide", "top", 260.0),
            right=Anchor("slide", "right", -60.0),
            bottom=Anchor("slide", "bottom", -60.0),
            width_mode="equal_share",
            reading_order=3,
            share_group="cols",
        ),
        "footer": SlotConstraints(
            left=Anchor("slide", "left", 60.0),
            top=Anchor("body", "bottom", 20.0),
            right=Anchor("slide", "right", -60.0),
            bottom=None,
            height_mode="fill_remaining",
            reading_order=4,
        ),
    }

    measurements: list[tuple[str, float]] = []

    def measure(slot_name: str, _content: object | None, width: float) -> float:
        measurements.append((slot_name, width))
        return 120.0

    rects = solve(constraints, {"body": "copy"}, measure, SLIDE_WIDTH_PT, SLIDE_HEIGHT_PT)

    assert rects["body"].height == pytest.approx(120.0)
    assert rects["col1"].width == pytest.approx(300.0)
    assert rects["col2"].width == pytest.approx(300.0)
    assert rects["col1"].x == pytest.approx(60.0)
    assert rects["col2"].x == pytest.approx(360.0)
    assert rects["footer"].y == pytest.approx(260.0)
    assert rects["footer"].height == pytest.approx(280.0)
    assert measurements == [("body", 600.0)]


def test_validate_constraints_raises_for_cycles() -> None:
    constraints = {
        "a": SlotConstraints(
            left=Anchor("slide", "left", 40.0),
            top=Anchor("b", "bottom", 10.0),
            right=Anchor("slide", "right", -40.0),
            bottom=Anchor("slide", "bottom", -40.0),
        ),
        "b": SlotConstraints(
            left=Anchor("slide", "left", 40.0),
            top=Anchor("a", "bottom", 10.0),
            right=Anchor("slide", "right", -40.0),
            bottom=Anchor("slide", "bottom", -40.0),
        ),
    }

    with pytest.raises(AgentSlidesError) as exc_info:
        validate_constraints(constraints)

    assert exc_info.value.code == INVALID_SLOT
    assert "cycle" in exc_info.value.message
