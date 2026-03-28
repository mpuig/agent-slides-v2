from __future__ import annotations

from importlib import resources

import pytest

from agent_slides.errors import AgentSlidesError, THEME_NOT_FOUND
from agent_slides.model.themes import list_themes, load_theme, resolve_style
from agent_slides.model.types import Theme


def test_load_theme_returns_theme() -> None:
    theme = load_theme("default")

    assert isinstance(theme, Theme)
    assert theme.name == "default"
    assert theme.fonts.heading == "Calibri"
    assert theme.spacing.margin == 60


def test_load_theme_raises_for_missing_theme() -> None:
    with pytest.raises(AgentSlidesError) as exc_info:
        load_theme("nonexistent")

    assert exc_info.value.code == THEME_NOT_FOUND


def test_list_themes_returns_default() -> None:
    assert list_themes() == ["default"]


def test_resolve_style_heading() -> None:
    theme = load_theme("default")

    assert resolve_style(theme, "heading") == {
        "font_family": "Calibri",
        "color": "#1a1a2e",
        "font_bold": True,
    }


def test_resolve_style_body() -> None:
    theme = load_theme("default")

    assert resolve_style(theme, "body") == {
        "font_family": "Calibri",
        "color": "#333333",
        "font_bold": False,
    }


def test_theme_resource_is_packaged() -> None:
    resource = resources.files("agent_slides.themes").joinpath("default.json")

    assert resource.is_file()
    assert '"name": "default"' in resource.read_text(encoding="utf-8")
