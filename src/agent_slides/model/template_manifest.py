"""Helpers for reading learned template manifests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, INVALID_LAYOUT, SCHEMA_ERROR
from agent_slides.model.layouts import get_layout
from agent_slides.model.themes import load_theme
from agent_slides.model.types import LayoutDef, TextFitting, Theme, ThemeColors, ThemeFonts, ThemeSpacing

_SUPPORTED_LAYOUTS: dict[tuple[str, ...], str] = {
    (): "blank",
    ("body",): "closing",
    ("heading", "subheading"): "title",
    ("heading", "body"): "title_content",
    ("quote", "attribution"): "quote",
    ("heading", "col1", "col2"): "two_col",
    ("heading", "col1", "col2", "col3"): "three_col",
    ("heading", "left_header", "left_body", "right_header", "right_body"): "comparison",
}


def read_template_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate the raw manifest payload."""

    manifest_path = Path(path)
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Manifest file not found: {manifest_path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest file is not valid JSON: {manifest_path}") from exc

    if not isinstance(payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest root must be a JSON object.")

    return payload


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be a non-empty string.")
    return value


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an array.")
    return value


def _require_dict(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an object.")
    return value


def _slot_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
    slot_name, placeholder_idx = item
    if isinstance(placeholder_idx, int):
        return (placeholder_idx, slot_name)
    return (10**9, slot_name)


def _ordered_slots(layout: dict[str, Any]) -> tuple[str, ...]:
    slot_mapping = _require_dict(layout, "slot_mapping")
    return tuple(slot_name for slot_name, _ in sorted(slot_mapping.items(), key=_slot_sort_key))


def extracted_theme_name(path: str | Path) -> str:
    """Derive a stable synthetic theme name from a manifest path."""

    stem = Path(path).name.removesuffix(".json")
    if stem.endswith(".manifest"):
        stem = stem.removesuffix(".manifest")
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-") or "template"
    return f"extracted-{slug}"


def load_template_theme(path: str | Path) -> Theme:
    """Load a manifest theme by overlaying it on the built-in default theme."""

    payload = read_template_manifest(path)
    theme_payload = payload.get("theme")
    if not isinstance(theme_payload, dict) or not theme_payload:
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme' must be a non-empty object.")

    base_theme = load_theme("default")

    colors_payload = theme_payload.get("colors", {})
    fonts_payload = theme_payload.get("fonts", {})
    spacing_payload = theme_payload.get("spacing", {})
    if not isinstance(colors_payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme.colors' must be an object.")
    if not isinstance(fonts_payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme.fonts' must be an object.")
    if not isinstance(spacing_payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme.spacing' must be an object.")

    colors = base_theme.colors.model_dump()
    colors.update(colors_payload)
    fonts = base_theme.fonts.model_dump()
    fonts.update(fonts_payload)
    spacing = base_theme.spacing.model_dump()
    spacing.update(spacing_payload)

    return Theme(
        name=extracted_theme_name(path),
        colors=ThemeColors(**colors),
        fonts=ThemeFonts(**fonts),
        spacing=ThemeSpacing(**spacing),
    )


class TemplateLayoutRegistry:
    """Expose supported manifest layouts through the LayoutProvider protocol."""

    def __init__(self, manifest_path: str | Path) -> None:
        payload = read_template_manifest(manifest_path)
        self._manifest_path = Path(manifest_path)
        self._layouts: dict[str, LayoutDef] = {}
        self._load(payload)

    def _load(self, payload: dict[str, Any]) -> None:
        _require_string(payload, "source")
        slide_masters = _require_list(payload, "slide_masters")

        for index, master in enumerate(slide_masters):
            if not isinstance(master, dict):
                raise AgentSlidesError(SCHEMA_ERROR, f"Manifest slide_masters[{index}] must be an object.")
            for layout_index, layout in enumerate(_require_list(master, "layouts")):
                if not isinstance(layout, dict):
                    raise AgentSlidesError(
                        SCHEMA_ERROR,
                        f"Manifest slide_masters[{index}].layouts[{layout_index}] must be an object.",
                    )
                slug = _require_string(layout, "slug")
                if slug in self._layouts:
                    raise AgentSlidesError(SCHEMA_ERROR, f"Manifest layout slug '{slug}' is duplicated.")

                slots = _ordered_slots(layout)
                builtin_name = _SUPPORTED_LAYOUTS.get(slots)
                if builtin_name is None:
                    continue

                builtin_layout = get_layout(builtin_name)
                self._layouts[slug] = builtin_layout.model_copy(update={"name": slug})

        if not self._layouts:
            raise AgentSlidesError(
                INVALID_LAYOUT,
                f"Manifest '{self._manifest_path}' does not define any supported layouts.",
            )

    def get_layout(self, slug: str) -> LayoutDef:
        try:
            return self._layouts[slug]
        except KeyError as exc:
            available = ", ".join(self.list_layouts())
            raise AgentSlidesError(
                INVALID_LAYOUT,
                f"Unknown layout '{slug}'. Available layouts: {available}",
            ) from exc

    def list_layouts(self) -> list[str]:
        return list(self._layouts)

    def get_slot_names(self, slug: str) -> list[str]:
        return list(self.get_layout(slug).slots)

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        return self.get_layout(slug).text_fitting[role]
