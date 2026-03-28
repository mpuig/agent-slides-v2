"""Built-in layout definitions for v0."""

from __future__ import annotations

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT
from agent_slides.model.types import GridDef, LayoutDef, SlotDef, TextFitting

SLIDE_WIDTH_PT = 720.0
SLIDE_HEIGHT_PT = 540.0
DEFAULT_MARGIN_PT = 60.0
DEFAULT_GUTTER_PT = 20.0

DEFAULT_TEXT_FITTING = {
    "heading": TextFitting(default_size=32.0, min_size=24.0),
    "body": TextFitting(default_size=18.0, min_size=10.0),
}


def _grid(*, columns: int, rows: int, row_heights: list[float], col_widths: list[float]) -> GridDef:
    return GridDef(
        columns=columns,
        rows=rows,
        row_heights=row_heights,
        col_widths=col_widths,
        margin=DEFAULT_MARGIN_PT,
        gutter=DEFAULT_GUTTER_PT,
    )


def _layout(
    *,
    name: str,
    slots: dict[str, SlotDef],
    grid: GridDef,
    text_fitting: dict[str, TextFitting],
) -> LayoutDef:
    return LayoutDef(
        name=name,
        slots=slots,
        grid=grid,
        text_fitting=text_fitting,
    )


def _text_slot(
    *,
    grid_row: int | list[int],
    grid_col: int | list[int],
    role: str,
    bg_color: str | None = None,
    bg_transparency: float = 0.0,
) -> SlotDef:
    return SlotDef(
        grid_row=grid_row,
        grid_col=grid_col,
        role=role,
        bg_color=bg_color,
        bg_transparency=bg_transparency,
    )


def _image_slot(
    *,
    grid_row: int | list[int],
    grid_col: int | list[int],
    full_bleed: bool = False,
) -> SlotDef:
    return SlotDef(
        grid_row=grid_row,
        grid_col=grid_col,
        role="image",
        full_bleed=full_bleed,
    )


LAYOUTS: dict[str, LayoutDef] = {
    "blank": _layout(
        name="blank",
        slots={},
        grid=_grid(columns=1, rows=1, row_heights=[1.0], col_widths=[1.0]),
        text_fitting={},
    ),
    "comparison": _layout(
        name="comparison",
        slots={
            "heading": SlotDef(grid_row=1, grid_col=[1, 2], role="heading"),
            "left_header": SlotDef(grid_row=2, grid_col=1, role="heading"),
            "left_body": SlotDef(grid_row=3, grid_col=1, role="body"),
            "right_header": SlotDef(grid_row=2, grid_col=2, role="heading"),
            "right_body": SlotDef(grid_row=3, grid_col=2, role="body"),
        },
        grid=_grid(columns=2, rows=3, row_heights=[0.12, 0.18, 0.70], col_widths=[0.5, 0.5]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "quote": _layout(
        name="quote",
        slots={
            "quote": SlotDef(grid_row=1, grid_col=1, role="quote"),
            "attribution": SlotDef(grid_row=2, grid_col=1, role="attribution"),
        },
        grid=_grid(columns=1, rows=2, row_heights=[0.70, 0.30], col_widths=[1.0]),
        text_fitting={
            "quote": TextFitting(default_size=28.0, min_size=20.0),
            "attribution": TextFitting(default_size=16.0, min_size=12.0),
        },
    ),
    "three_col": _layout(
        name="three_col",
        slots={
            "heading": SlotDef(grid_row=1, grid_col=[1, 2, 3], role="heading"),
            "col1": SlotDef(grid_row=2, grid_col=1, role="body"),
            "col2": SlotDef(grid_row=2, grid_col=2, role="body"),
            "col3": SlotDef(grid_row=2, grid_col=3, role="body"),
        },
        grid=_grid(
            columns=3,
            rows=2,
            row_heights=[0.12, 0.88],
            col_widths=[1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0],
        ),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "title": _layout(
        name="title",
        slots={
            "heading": SlotDef(grid_row=1, grid_col=1, role="heading"),
            "subheading": SlotDef(grid_row=2, grid_col=1, role="body"),
        },
        grid=_grid(columns=1, rows=2, row_heights=[0.40, 0.60], col_widths=[1.0]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "title_content": _layout(
        name="title_content",
        slots={
            "heading": SlotDef(grid_row=1, grid_col=1, role="heading"),
            "body": SlotDef(grid_row=2, grid_col=1, role="body"),
        },
        grid=_grid(columns=1, rows=2, row_heights=[0.12, 0.88], col_widths=[1.0]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "two_col": _layout(
        name="two_col",
        slots={
            "heading": SlotDef(grid_row=1, grid_col=[1, 2], role="heading"),
            "col1": SlotDef(grid_row=2, grid_col=1, role="body"),
            "col2": SlotDef(grid_row=2, grid_col=2, role="body"),
        },
        grid=_grid(columns=2, rows=2, row_heights=[0.12, 0.88], col_widths=[0.5, 0.5]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "closing": _layout(
        name="closing",
        slots={
            "body": _text_slot(grid_row=1, grid_col=1, role="body"),
        },
        grid=_grid(columns=1, rows=1, row_heights=[1.0], col_widths=[1.0]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "image_left": _layout(
        name="image_left",
        slots={
            "image": _image_slot(grid_row=[1, 2], grid_col=1),
            "heading": _text_slot(grid_row=1, grid_col=2, role="heading"),
            "body": _text_slot(grid_row=2, grid_col=2, role="body"),
        },
        grid=_grid(columns=2, rows=2, row_heights=[0.28, 0.72], col_widths=[0.5, 0.5]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "image_right": _layout(
        name="image_right",
        slots={
            "heading": _text_slot(grid_row=1, grid_col=1, role="heading"),
            "body": _text_slot(grid_row=2, grid_col=1, role="body"),
            "image": _image_slot(grid_row=[1, 2], grid_col=2),
        },
        grid=_grid(columns=2, rows=2, row_heights=[0.28, 0.72], col_widths=[0.5, 0.5]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "hero_image": _layout(
        name="hero_image",
        slots={
            "image": _image_slot(grid_row=[1, 2, 3], grid_col=1, full_bleed=True),
            "heading": _text_slot(
                grid_row=2,
                grid_col=1,
                role="heading",
                bg_color="#FFFFFF",
                bg_transparency=0.25,
            ),
            "subheading": _text_slot(
                grid_row=3,
                grid_col=1,
                role="body",
                bg_color="#FFFFFF",
                bg_transparency=0.25,
            ),
        },
        grid=_grid(columns=1, rows=3, row_heights=[0.20, 0.36, 0.44], col_widths=[1.0]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
    "gallery": _layout(
        name="gallery",
        slots={
            "heading": _text_slot(grid_row=1, grid_col=[1, 2], role="heading"),
            "img1": _image_slot(grid_row=2, grid_col=1),
            "img2": _image_slot(grid_row=2, grid_col=2),
            "img3": _image_slot(grid_row=3, grid_col=1),
            "img4": _image_slot(grid_row=3, grid_col=2),
        },
        grid=_grid(columns=2, rows=3, row_heights=[0.16, 0.42, 0.42], col_widths=[0.5, 0.5]),
        text_fitting=DEFAULT_TEXT_FITTING,
    ),
}


def _load_layout(name: str) -> LayoutDef:
    """Return a built-in layout definition by name."""
    try:
        return LAYOUTS[name]
    except KeyError as exc:
        available = ", ".join(list_layouts())
        raise AgentSlidesError(INVALID_LAYOUT, f"Unknown layout '{name}'. Available layouts: {available}") from exc


def get_layout(name: str) -> LayoutDef:
    """Return a built-in layout definition by name."""

    return _load_layout(name)


def list_layouts() -> list[str]:
    """Return the sorted list of available built-in layouts."""

    return sorted(LAYOUTS)

def get_slot_names(name: str) -> list[str]:
    """Return slot names for a built-in layout."""

    layout_loader = get_layout
    return list(layout_loader(name).slots)


def get_text_fitting(name: str, role: str) -> TextFitting:
    """Return text fitting rules for a built-in layout role."""

    layout_loader = get_layout
    return layout_loader(name).text_fitting[role]
