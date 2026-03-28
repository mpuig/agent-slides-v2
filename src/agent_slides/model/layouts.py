"""Built-in layout definitions."""

from __future__ import annotations

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT
from agent_slides.model.types import GridDef, LayoutDef, SlotDef, TextFitting

_LAYOUTS: dict[str, LayoutDef] = {
    "title": LayoutDef(
        name="title",
        slots={
            "heading": SlotDef(grid_row=0, grid_col=0, role="heading"),
            "subheading": SlotDef(grid_row=1, grid_col=0, role="body"),
        },
        grid=GridDef(
            columns=1,
            rows=2,
            row_heights=[0.6, 0.4],
            col_widths=[1.0],
            margin=48.0,
            gutter=24.0,
        ),
        text_fitting={
            "heading": TextFitting(default_size=30.0, min_size=20.0),
            "subheading": TextFitting(default_size=20.0, min_size=14.0),
        },
    ),
    "two_col": LayoutDef(
        name="two_col",
        slots={
            "heading": SlotDef(grid_row=0, grid_col=[0, 1], role="heading"),
            "col1": SlotDef(grid_row=1, grid_col=0, role="body"),
            "col2": SlotDef(grid_row=1, grid_col=1, role="body"),
        },
        grid=GridDef(
            columns=2,
            rows=2,
            row_heights=[0.25, 0.75],
            col_widths=[0.5, 0.5],
            margin=48.0,
            gutter=24.0,
        ),
        text_fitting={
            "heading": TextFitting(default_size=28.0, min_size=18.0),
            "col1": TextFitting(default_size=18.0, min_size=12.0),
            "col2": TextFitting(default_size=18.0, min_size=12.0),
        },
    ),
    "three_col": LayoutDef(
        name="three_col",
        slots={
            "heading": SlotDef(grid_row=0, grid_col=[0, 1, 2], role="heading"),
            "col1": SlotDef(grid_row=1, grid_col=0, role="body"),
            "col2": SlotDef(grid_row=1, grid_col=1, role="body"),
            "col3": SlotDef(grid_row=1, grid_col=2, role="body"),
        },
        grid=GridDef(
            columns=3,
            rows=2,
            row_heights=[0.25, 0.75],
            col_widths=[0.333333, 0.333333, 0.333334],
            margin=48.0,
            gutter=24.0,
        ),
        text_fitting={
            "heading": TextFitting(default_size=28.0, min_size=18.0),
            "col1": TextFitting(default_size=16.0, min_size=12.0),
            "col2": TextFitting(default_size=16.0, min_size=12.0),
            "col3": TextFitting(default_size=16.0, min_size=12.0),
        },
    ),
}


def list_layouts() -> list[str]:
    """Return the available built-in layout names."""

    return sorted(_LAYOUTS)


def get_layout(name: str) -> LayoutDef:
    """Return a built-in layout or raise a uniform domain error."""

    layout = _LAYOUTS.get(name)
    if layout is None:
        available = ", ".join(list_layouts())
        raise AgentSlidesError(
            INVALID_LAYOUT,
            f"Layout {name!r} is invalid. Available layouts: {available}",
        )
    return layout

