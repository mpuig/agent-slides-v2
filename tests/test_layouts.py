from __future__ import annotations

from math import isclose

import pytest

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT
from agent_slides.model.layouts import get_layout, list_layouts


EXPECTED_LAYOUTS = [
    "blank",
    "comparison",
    "quote",
    "three_col",
    "title",
    "title_content",
    "two_col",
]

EXPECTED_SLOTS = {
    "blank": {},
    "comparison": {
        "title": "heading",
        "left_header": "heading",
        "left_body": "body",
        "right_header": "heading",
        "right_body": "body",
    },
    "quote": {
        "quote": "quote",
        "attribution": "attribution",
    },
    "three_col": {
        "title": "heading",
        "col1": "body",
        "col2": "body",
        "col3": "body",
    },
    "title": {
        "title": "heading",
        "subtitle": "body",
    },
    "title_content": {
        "title": "heading",
        "body": "body",
    },
    "two_col": {
        "title": "heading",
        "col1": "body",
        "col2": "body",
    },
}


def test_list_layouts_returns_sorted_names() -> None:
    assert list_layouts() == EXPECTED_LAYOUTS


@pytest.mark.parametrize("name", EXPECTED_LAYOUTS)
def test_get_layout_returns_all_builtins(name: str) -> None:
    layout = get_layout(name)

    assert layout.name == name
    assert {slot_name: slot.role for slot_name, slot in layout.slots.items()} == EXPECTED_SLOTS[name]


def test_get_layout_raises_invalid_layout_error_for_unknown_name() -> None:
    with pytest.raises(AgentSlidesError) as exc_info:
        get_layout("invalid")

    assert exc_info.value.code == INVALID_LAYOUT
    assert "invalid" in str(exc_info.value)
    for layout_name in EXPECTED_LAYOUTS:
        assert layout_name in str(exc_info.value)


@pytest.mark.parametrize("name", EXPECTED_LAYOUTS)
def test_all_layout_grids_and_text_rules_are_valid(name: str) -> None:
    layout = get_layout(name)

    assert layout.grid.rows == len(layout.grid.row_heights)
    assert layout.grid.columns == len(layout.grid.col_widths)
    assert isclose(sum(layout.grid.row_heights), 1.0, rel_tol=0.0, abs_tol=1e-9)
    assert isclose(sum(layout.grid.col_widths), 1.0, rel_tol=0.0, abs_tol=1e-9)

    for slot in layout.slots.values():
        assert slot.role in layout.text_fitting


def test_multi_column_titles_span_all_columns() -> None:
    assert get_layout("two_col").slots["title"].grid_col == [1, 2]
    assert get_layout("three_col").slots["title"].grid_col == [1, 2, 3]
    assert get_layout("comparison").slots["title"].grid_col == [1, 2]


def test_quote_layout_uses_custom_text_fitting() -> None:
    layout = get_layout("quote")

    assert layout.text_fitting["quote"].default_size == 28.0
    assert layout.text_fitting["quote"].min_size == 20.0
    assert layout.text_fitting["attribution"].default_size == 16.0
    assert layout.text_fitting["attribution"].min_size == 12.0
