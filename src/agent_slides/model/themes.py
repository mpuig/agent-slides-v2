"""Theme loading and style resolution."""

from __future__ import annotations

import json
from importlib import resources

from agent_slides.errors import (
    AgentSlidesError,
    THEME_INVALID,
    THEME_NOT_FOUND,
    THEME_ROLE_NOT_FOUND,
)
from agent_slides.model.types import Theme, ThemeColors, ThemeFonts, ThemeSpacing


def _theme_package() -> resources.abc.Traversable:
    return resources.files("agent_slides.themes")


def load_theme(name: str) -> Theme:
    """Load a built-in theme by name."""

    resource = _theme_package().joinpath(f"{name}.json")
    if not resource.is_file():
        raise AgentSlidesError(
            code=THEME_NOT_FOUND,
            message=f"Theme '{name}' was not found.",
        )

    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
        return Theme(
            name=payload["name"],
            colors=ThemeColors(**payload["colors"]),
            fonts=ThemeFonts(**payload["fonts"]),
            spacing=ThemeSpacing(**payload["spacing"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AgentSlidesError(
            code=THEME_INVALID,
            message=f"Theme '{name}' is invalid.",
        ) from exc


def list_themes() -> list[str]:
    """Return the built-in theme names."""

    return sorted(
        path.name.removesuffix(".json")
        for path in _theme_package().iterdir()
        if path.is_file() and path.name.endswith(".json")
    )


def resolve_style(theme: Theme, role: str) -> dict[str, str | bool]:
    """Resolve a semantic role to concrete typography and color values."""

    if role == "heading":
        return {
            "font_family": theme.fonts.heading,
            "color": theme.colors.heading_text,
            "font_bold": True,
        }
    if role in {"body", "quote"}:
        return {
            "font_family": theme.fonts.body,
            "color": theme.colors.text,
            "font_bold": False,
        }
    if role == "attribution":
        return {
            "font_family": theme.fonts.body,
            "color": theme.colors.subtle_text,
            "font_bold": False,
        }
    if role == "image":
        return {
            "font_family": theme.fonts.body,
            "color": theme.colors.text,
            "font_bold": False,
        }
    raise AgentSlidesError(
        code=THEME_ROLE_NOT_FOUND,
        message=f"Role '{role}' is not defined by the theme system.",
    )
