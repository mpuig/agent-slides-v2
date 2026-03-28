"""Layout provider protocol and manifest-backed implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, INVALID_LAYOUT, SCHEMA_ERROR
from agent_slides.model.layouts import (
    DEFAULT_GUTTER_PT,
    DEFAULT_MARGIN_PT,
    get_layout,
    get_slot_names,
    get_text_fitting,
    list_layouts,
)
from agent_slides.model.types import GridDef, LayoutDef, SlotDef, TextFitting, Theme


class LayoutProvider(Protocol):
    def get_layout(self, slug: str) -> LayoutDef: ...

    def list_layouts(self) -> list[str]: ...

    def get_slot_names(self, slug: str) -> list[str]: ...

    def get_text_fitting(self, slug: str, role: str) -> TextFitting: ...


class BuiltinLayoutProvider:
    """Wrap the built-in layout registry behind the LayoutProvider protocol."""

    def get_layout(self, slug: str) -> LayoutDef:
        return get_layout(slug)

    def list_layouts(self) -> list[str]:
        return list_layouts()

    def get_slot_names(self, slug: str) -> list[str]:
        return get_slot_names(slug)

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        return get_text_fitting(slug, role)


_TEMPLATE_TEXT_FITTING = {
    "heading": TextFitting(default_size=32.0, min_size=24.0),
    "body": TextFitting(default_size=18.0, min_size=10.0),
    "quote": TextFitting(default_size=28.0, min_size=20.0),
    "attribution": TextFitting(default_size=16.0, min_size=12.0),
    "image": TextFitting(default_size=18.0, min_size=10.0),
}
_PLACEHOLDER_ROLE_BY_TYPE = {
    "TITLE": "heading",
    "SUBTITLE": "body",
    "BODY": "body",
    "PICTURE": "image",
}


def _template_grid() -> GridDef:
    return GridDef(
        columns=1,
        rows=1,
        row_heights=[1.0],
        col_widths=[1.0],
        margin=DEFAULT_MARGIN_PT,
        gutter=DEFAULT_GUTTER_PT,
    )


def _role_from_slot(slot_name: str, placeholder_type: str) -> str:
    if slot_name == "heading":
        return "heading"
    if slot_name == "quote":
        return "quote"
    if slot_name == "attribution":
        return "attribution"
    if slot_name == "image" or slot_name.startswith("img"):
        return "image"
    if slot_name == "subheading" or slot_name == "body":
        return "body"
    if slot_name.startswith("col") or slot_name.endswith("_body"):
        return "body"
    return _PLACEHOLDER_ROLE_BY_TYPE.get(placeholder_type, "body")


def _require_manifest_dict(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an object.")
    return value


def _require_manifest_list(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an array.")
    return value


class TemplateLayoutRegistry:
    """Layout provider backed by a learned template manifest."""

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = str(Path(manifest_path).resolve())
        payload = self._read_manifest(Path(self.manifest_path))
        self.theme = self._load_theme(payload)
        self._layouts: dict[str, LayoutDef] = {}
        self._placeholders_by_slot: dict[str, dict[str, dict[str, object]]] = {}
        self._load_layouts(payload)

    def _read_manifest(self, manifest_path: Path) -> dict[str, object]:
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

    def _load_theme(self, payload: dict[str, object]) -> Theme:
        raw_theme = _require_manifest_dict(payload.get("theme"), field="theme")
        try:
            return Theme.model_validate({"name": "template", **raw_theme})
        except ValidationError as exc:
            raise AgentSlidesError(SCHEMA_ERROR, "Manifest field 'theme' is invalid.") from exc

    def _load_layouts(self, payload: dict[str, object]) -> None:
        masters = _require_manifest_list(payload.get("slide_masters"), field="slide_masters")
        for master_index, master in enumerate(masters):
            master_dict = _require_manifest_dict(master, field=f"slide_masters[{master_index}]")
            layouts = _require_manifest_list(
                master_dict.get("layouts"),
                field=f"slide_masters[{master_index}].layouts",
            )
            for layout_index, layout in enumerate(layouts):
                self._register_layout(
                    _require_manifest_dict(
                        layout,
                        field=f"slide_masters[{master_index}].layouts[{layout_index}]",
                    )
                )

    def _register_layout(self, layout_payload: dict[str, object]) -> None:
        slug = layout_payload.get("slug")
        if not isinstance(slug, str) or not slug:
            raise AgentSlidesError(SCHEMA_ERROR, "Manifest layout field 'slug' must be a non-empty string.")
        if slug in self._layouts:
            raise AgentSlidesError(SCHEMA_ERROR, f"Manifest layout slug '{slug}' is duplicated.")

        placeholders = _require_manifest_list(layout_payload.get("placeholders", []), field=f"layout '{slug}'.placeholders")
        slot_mapping = _require_manifest_dict(layout_payload.get("slot_mapping", {}), field=f"layout '{slug}'.slot_mapping")

        placeholders_by_idx: dict[int, dict[str, object]] = {}
        for placeholder in placeholders:
            placeholder_dict = _require_manifest_dict(placeholder, field=f"layout '{slug}'.placeholders[]")
            idx = placeholder_dict.get("idx")
            bounds = _require_manifest_dict(placeholder_dict.get("bounds"), field=f"layout '{slug}'.placeholders[].bounds")
            placeholder_type = placeholder_dict.get("type")
            if not isinstance(idx, int):
                raise AgentSlidesError(SCHEMA_ERROR, f"Manifest placeholder idx for layout '{slug}' must be an integer.")
            if not isinstance(placeholder_type, str) or not placeholder_type:
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest placeholder type for layout '{slug}' idx {idx} must be a non-empty string.",
                )
            for axis in ("x", "y", "w", "h"):
                if not isinstance(bounds.get(axis), int | float):
                    raise AgentSlidesError(
                        SCHEMA_ERROR,
                        f"Manifest placeholder bounds '{axis}' for layout '{slug}' idx {idx} must be numeric.",
                    )
            placeholders_by_idx[idx] = placeholder_dict

        slots: dict[str, SlotDef] = {}
        text_fitting: dict[str, TextFitting] = {}
        placeholders_by_slot: dict[str, dict[str, object]] = {}

        for slot_name, raw_idx in slot_mapping.items():
            if not isinstance(slot_name, str) or not slot_name:
                raise AgentSlidesError(SCHEMA_ERROR, f"Manifest slot name for layout '{slug}' must be a non-empty string.")
            if not isinstance(raw_idx, int):
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest slot mapping for layout '{slug}' slot '{slot_name}' must be an integer placeholder idx.",
                )

            placeholder = placeholders_by_idx.get(raw_idx)
            if placeholder is None:
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest layout '{slug}' maps slot '{slot_name}' to missing placeholder idx {raw_idx}.",
                )

            role = _role_from_slot(slot_name, str(placeholder["type"]))
            slots[slot_name] = SlotDef(grid_row=1, grid_col=1, role=role)
            text_fitting[role] = _TEMPLATE_TEXT_FITTING[role]
            placeholders_by_slot[slot_name] = placeholder

        self._layouts[slug] = LayoutDef(
            name=slug,
            slots=slots,
            grid=_template_grid(),
            text_fitting=text_fitting,
        )
        self._placeholders_by_slot[slug] = placeholders_by_slot

    def get_layout(self, slug: str) -> LayoutDef:
        try:
            return self._layouts[slug]
        except KeyError as exc:
            available = ", ".join(self.list_layouts())
            raise AgentSlidesError(INVALID_LAYOUT, f"Unknown layout '{slug}'. Available layouts: {available}") from exc

    def list_layouts(self) -> list[str]:
        return sorted(self._layouts)

    def get_slot_names(self, slug: str) -> list[str]:
        return list(self.get_layout(slug).slots)

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        return self.get_layout(slug).text_fitting[role]

    def get_placeholder(self, slug: str, slot_name: str) -> dict[str, object]:
        layout_placeholders = self._placeholders_by_slot.get(slug)
        if layout_placeholders is None or slot_name not in layout_placeholders:
            raise AgentSlidesError(
                INVALID_LAYOUT,
                f"Layout '{slug}' does not define placeholder bounds for slot '{slot_name}'.",
            )
        return layout_placeholders[slot_name]


def resolve_layout_provider(template_manifest: str | None) -> LayoutProvider:
    """Resolve the active layout provider for a deck."""

    if template_manifest is None:
        return BuiltinLayoutProvider()
    return TemplateLayoutRegistry(template_manifest)
