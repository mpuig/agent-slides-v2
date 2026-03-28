"""Template-backed layout registry loaded from a learned manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT, SCHEMA_ERROR
from agent_slides.model.layouts import DEFAULT_TEXT_FITTING
from agent_slides.model.themes import load_theme
from agent_slides.model.types import GridDef, LayoutDef, SlotDef, TextFitting, Theme, ThemeColors, ThemeFonts, ThemeSpacing

_TEMPLATE_GRID = GridDef(
    columns=1,
    rows=1,
    row_heights=[1.0],
    col_widths=[1.0],
    margin=0.0,
    gutter=0.0,
)
_THEME_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _as_dict(value: object, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentSlidesError(SCHEMA_ERROR, f"{context} must be an object")
    return dict(value)


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentSlidesError(SCHEMA_ERROR, f"{context} must be a non-empty string")
    return value.strip()


def _optional_number(mapping: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{key}' must be numeric")
        return float(value)
    return None


def _infer_role(slot_name: str, slot_mapping: dict[str, Any]) -> str:
    explicit = slot_mapping.get("role")
    if isinstance(explicit, str) and explicit:
        return explicit.lower()

    placeholder_type = slot_mapping.get("type")
    if isinstance(placeholder_type, str):
        normalized = placeholder_type.upper()
        if normalized == "PICTURE":
            return "image"

    lowered = slot_name.lower()
    if lowered in {"heading", "title", "header"}:
        return "heading"
    if lowered in {"subheading", "subtitle"}:
        return "body"
    if lowered in {"quote"}:
        return "quote"
    if lowered in {"attribution", "credit", "citation"}:
        return "attribution"
    if "image" in lowered or lowered.startswith("img"):
        return "image"
    return "body"


def _coerce_slot_mapping(
    slot_name: str,
    raw_slot: object,
    *,
    placeholders_by_idx: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(raw_slot, bool):
        raise AgentSlidesError(SCHEMA_ERROR, f"slot_mapping[{slot_name!r}] must not be a boolean")
    if isinstance(raw_slot, int):
        try:
            placeholder = placeholders_by_idx[raw_slot]
        except KeyError as exc:
            raise AgentSlidesError(
                SCHEMA_ERROR,
                f"slot_mapping[{slot_name!r}] references missing placeholder idx {raw_slot}",
            ) from exc
        return {
            "type": placeholder.get("type"),
            "bounds": placeholder.get("bounds"),
        }
    return _as_dict(raw_slot, context=f"slot_mapping[{slot_name!r}]")


def _build_slot(
    slot_name: str,
    raw_slot: object,
    *,
    placeholders_by_idx: dict[int, dict[str, Any]],
) -> SlotDef:
    slot_mapping = _coerce_slot_mapping(
        slot_name,
        raw_slot,
        placeholders_by_idx=placeholders_by_idx,
    )
    raw_bounds = slot_mapping.get("bounds", slot_mapping)
    bounds = _as_dict(raw_bounds, context=f"slot_mapping[{slot_name!r}] bounds")
    role = _infer_role(slot_name, slot_mapping)

    return SlotDef(
        grid_row=1,
        grid_col=1,
        role=role,
        x=_optional_number(bounds, "x", "left"),
        y=_optional_number(bounds, "y", "top"),
        width=_optional_number(bounds, "width", "w"),
        height=_optional_number(bounds, "height", "h"),
        bg_color=slot_mapping.get("bg_color"),
        bg_transparency=float(slot_mapping.get("bg_transparency", 0.0)),
        full_bleed=bool(slot_mapping.get("full_bleed", False)),
    )


def _default_text_fitting(role: str) -> TextFitting:
    if role == "heading":
        return DEFAULT_TEXT_FITTING["heading"]
    return DEFAULT_TEXT_FITTING["body"]


def _coerce_layouts(raw_layouts: object) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(raw_layouts, dict):
        return [(str(slug), _as_dict(value, context=f"layout[{slug!r}]")) for slug, value in raw_layouts.items()]
    if isinstance(raw_layouts, list):
        items: list[tuple[str, dict[str, Any]]] = []
        for index, value in enumerate(raw_layouts):
            layout = _as_dict(value, context=f"layouts[{index}]")
            slug = _require_string(layout.get("slug") or layout.get("name"), context=f"layouts[{index}].slug")
            items.append((slug, layout))
        return items
    raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'layouts' must be a list or object")


def _coerce_layout_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_layouts = manifest.get("layouts")
    if raw_layouts is not None:
        entries: list[dict[str, Any]] = []
        for index, (slug, layout) in enumerate(_coerce_layouts(raw_layouts)):
            entry = dict(layout)
            entry.setdefault("slug", slug)
            entry.setdefault("index", index)
            entry.setdefault("master_index", 0)
            entries.append(entry)
        return entries

    raw_masters = manifest.get("slide_masters", [])
    if not isinstance(raw_masters, list):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'slide_masters' must be an array")

    entries: list[dict[str, Any]] = []
    for master_index, raw_master in enumerate(raw_masters):
        master = _as_dict(raw_master, context=f"slide_masters[{master_index}]")
        manifest_master_index = master.get("index", master_index)
        for layout_index, raw_layout in enumerate(_coerce_layouts(master.get("layouts", []))):
            slug, layout = raw_layout
            entry = dict(layout)
            entry.setdefault("slug", slug)
            entry.setdefault("index", layout_index)
            entry.setdefault("master_index", manifest_master_index)
            entries.append(entry)
    return entries


def _coerce_placeholder_index(raw_placeholders: object, *, slug: str) -> dict[int, dict[str, Any]]:
    if raw_placeholders is None:
        return {}
    if not isinstance(raw_placeholders, list):
        raise AgentSlidesError(SCHEMA_ERROR, f"layout[{slug!r}].placeholders must be an array")

    placeholders: dict[int, dict[str, Any]] = {}
    for index, raw_placeholder in enumerate(raw_placeholders):
        placeholder = _as_dict(raw_placeholder, context=f"layout[{slug!r}].placeholders[{index}]")
        raw_idx = placeholder.get("idx")
        if isinstance(raw_idx, bool) or not isinstance(raw_idx, int):
            raise AgentSlidesError(SCHEMA_ERROR, f"layout[{slug!r}].placeholders[{index}].idx must be an integer")
        placeholders[raw_idx] = placeholder
    return placeholders


class TemplateLayoutRegistry:
    """Loads layouts from a template manifest and implements LayoutProvider."""

    def __init__(self, manifest_path: str):
        self._manifest_path = Path(manifest_path).expanduser().resolve(strict=False)
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AgentSlidesError(SCHEMA_ERROR, f"Template manifest not found: {self._manifest_path}") from exc
        except json.JSONDecodeError as exc:
            raise AgentSlidesError(
                SCHEMA_ERROR,
                (
                    f"Invalid JSON in template manifest {self._manifest_path}: "
                    f"{exc.msg} at line {exc.lineno} column {exc.colno}"
                ),
            ) from exc

        manifest = _as_dict(payload, context="template manifest")
        self._source_path = self._resolve_source_path(manifest)
        self._source_hash = self._resolve_source_hash(manifest)
        self._theme = self._resolve_theme(manifest)
        self._layouts: dict[str, LayoutDef] = {}
        self._slot_names: dict[str, list[str]] = {}
        self._layout_refs: dict[str, tuple[int, int]] = {}
        self._usable_layouts: list[str] = []
        self._load_layouts(manifest)

    def _load_layouts(self, manifest: dict[str, Any]) -> None:
        for raw_layout in _coerce_layout_entries(manifest):
            slug = _require_string(raw_layout.get("slug"), context="layout.slug")
            slot_mapping = _as_dict(raw_layout.get("slot_mapping", {}), context=f"layout[{slug!r}].slot_mapping")
            placeholders_by_idx = _coerce_placeholder_index(raw_layout.get("placeholders"), slug=slug)
            slots = {
                slot_name: _build_slot(
                    slot_name,
                    slot_value,
                    placeholders_by_idx=placeholders_by_idx,
                )
                for slot_name, slot_value in slot_mapping.items()
            }
            text_fitting = {
                slot.role: _default_text_fitting(slot.role)
                for slot in slots.values()
                if slot.role != "image"
            }
            self._layouts[slug] = LayoutDef(
                name=slug,
                slots=slots,
                grid=_TEMPLATE_GRID,
                text_fitting=text_fitting,
            )
            self._slot_names[slug] = list(slot_mapping)
            master_index = raw_layout.get("master_index", 0)
            layout_index = raw_layout.get("index", 0)
            if isinstance(master_index, bool) or not isinstance(master_index, int):
                raise AgentSlidesError(SCHEMA_ERROR, f"layout[{slug!r}].master_index must be an integer")
            if isinstance(layout_index, bool) or not isinstance(layout_index, int):
                raise AgentSlidesError(SCHEMA_ERROR, f"layout[{slug!r}].index must be an integer")
            self._layout_refs[slug] = (master_index, layout_index)
            if bool(raw_layout.get("usable", raw_layout.get("is_usable", True))):
                self._usable_layouts.append(slug)

    def _resolve_source_path(self, manifest: dict[str, Any]) -> str:
        raw_source = manifest.get("source")
        if isinstance(raw_source, dict):
            raw_source = raw_source.get("path")
        source = _require_string(raw_source, context="manifest source")
        return str((self._manifest_path.parent / source).resolve(strict=False))

    def _resolve_source_hash(self, manifest: dict[str, Any]) -> str:
        raw_source = manifest.get("source")
        if isinstance(raw_source, dict):
            for key in ("sha256", "hash", "source_hash"):
                value = raw_source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("source_hash", "source_sha256", "sha256"):
            value = manifest.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise AgentSlidesError(SCHEMA_ERROR, "Template manifest is missing source hash metadata")

    def _resolve_theme(self, manifest: dict[str, Any]) -> Theme:
        default_theme = load_theme("default")
        raw_theme = manifest.get("theme", {})
        if not isinstance(raw_theme, dict):
            raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme' must be an object")

        raw_name = raw_theme.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            theme_name = raw_name.strip()
        else:
            stem = self._manifest_path.name.removesuffix(".json")
            if stem.endswith(".manifest"):
                stem = stem.removesuffix(".manifest")
            slug = _THEME_SLUG_PATTERN.sub("-", stem.casefold()).strip("-") or "template"
            theme_name = f"extracted-{slug}"

        raw_colors = raw_theme.get("colors", {})
        raw_fonts = raw_theme.get("fonts", {})
        raw_spacing = raw_theme.get("spacing", {})
        if not isinstance(raw_colors, dict) or not isinstance(raw_fonts, dict) or not isinstance(raw_spacing, dict):
            raise AgentSlidesError(SCHEMA_ERROR, "Template theme colors, fonts, and spacing must be objects")

        return Theme(
            name=theme_name,
            colors=ThemeColors(
                primary=str(raw_colors.get("primary", default_theme.colors.primary)),
                secondary=str(raw_colors.get("secondary", default_theme.colors.secondary)),
                accent=str(raw_colors.get("accent", default_theme.colors.accent)),
                background=str(raw_colors.get("background", default_theme.colors.background)),
                text=str(raw_colors.get("text", raw_colors.get("foreground", default_theme.colors.text))),
                heading_text=(
                    str(raw_colors["heading_text"])
                    if "heading_text" in raw_colors
                    else default_theme.colors.heading_text
                ),
                subtle_text=(
                    str(raw_colors["subtle_text"])
                    if "subtle_text" in raw_colors
                    else default_theme.colors.subtle_text
                ),
            ),
            fonts=ThemeFonts(
                heading=str(raw_fonts.get("heading", default_theme.fonts.heading)),
                body=str(raw_fonts.get("body", default_theme.fonts.body)),
            ),
            spacing=ThemeSpacing(
                base_unit=float(raw_spacing.get("base_unit", default_theme.spacing.base_unit)),
                margin=float(raw_spacing.get("margin", default_theme.spacing.margin)),
                gutter=float(raw_spacing.get("gutter", default_theme.spacing.gutter)),
            ),
        )

    def get_layout(self, slug: str) -> LayoutDef:
        if slug not in self._layouts or slug not in self._usable_layouts:
            available = ", ".join(self.list_layouts())
            raise AgentSlidesError(
                INVALID_LAYOUT,
                f"Unknown layout '{slug}'. Available layouts: {available}",
            )
        return self._layouts[slug]

    def list_layouts(self) -> list[str]:
        return list(self._usable_layouts)

    def get_slot_names(self, slug: str) -> list[str]:
        layout = self.get_layout(slug)
        return list(self._slot_names[layout.name])

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        layout = self.get_layout(slug)
        if role in layout.text_fitting:
            return layout.text_fitting[role]
        return _default_text_fitting(role)

    def get_layout_ref(self, slug: str) -> tuple[int, int]:
        self.get_layout(slug)
        return self._layout_refs[slug]

    @property
    def source_path(self) -> str:
        return self._source_path

    @property
    def source_hash(self) -> str:
        return self._source_hash

    @property
    def theme(self) -> Theme:
        return self._theme
