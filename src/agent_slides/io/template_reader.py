"""Read PPTX templates and emit layout manifest JSON."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET
from zipfile import BadZipFile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.model.layouts import DEFAULT_GUTTER_PT, DEFAULT_MARGIN_PT
from agent_slides.model.types import EMU_PER_POINT
from agent_slides.template_slots import infer_template_slot_role

DEFAULT_BASE_UNIT_PT = 10.0
BODY_ROW_THRESHOLD_PT = 54.0
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
THEME_RELATIONSHIP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
DRAWINGML_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
NON_PLACEHOLDER_IDX_OFFSET = 1_000_000
BODY_SLOT_TYPES = {"BODY", "TEXT_BOX", "TABLE", "CHART", "GROUP"}
SPECIAL_SLOT_TYPES = {"quote", "attribution"}

_PLACEHOLDER_TYPE_MAP = {
    PP_PLACEHOLDER.TITLE: "TITLE",
    PP_PLACEHOLDER.CENTER_TITLE: "TITLE",
    PP_PLACEHOLDER.VERTICAL_TITLE: "TITLE",
    PP_PLACEHOLDER.SUBTITLE: "SUBTITLE",
    PP_PLACEHOLDER.BODY: "BODY",
    PP_PLACEHOLDER.OBJECT: "BODY",
    PP_PLACEHOLDER.VERTICAL_BODY: "BODY",
    PP_PLACEHOLDER.VERTICAL_OBJECT: "BODY",
    PP_PLACEHOLDER.PICTURE: "PICTURE",
    PP_PLACEHOLDER.TABLE: "TABLE",
    PP_PLACEHOLDER.CHART: "CHART",
}
_WARNING_ONLY_PLACEHOLDERS = {
    PP_PLACEHOLDER.MEDIA_CLIP,
    PP_PLACEHOLDER.ORG_CHART,
}


@dataclass(frozen=True)
class LearnResult:
    manifest_path: Path
    manifest: dict[str, object]
    layouts_found: int
    usable_layouts: int
    warnings: list[str]

    @property
    def source(self) -> str:
        return str(self.manifest["source"])


def read_template_manifest(
    template_path: str | Path,
    output_path: str | Path | None = None,
) -> LearnResult:
    """Read a PPTX template and persist its manifest JSON."""

    source_path = Path(template_path)
    if not source_path.exists():
        raise AgentSlidesError(FILE_NOT_FOUND, f"Template file not found: {source_path}")

    manifest_path = Path(output_path) if output_path is not None else _default_manifest_path(source_path)
    presentation = _open_presentation(source_path)
    return _build_manifest(source_path, manifest_path, presentation)


def _default_manifest_path(template_path: Path) -> Path:
    return template_path.with_name(f"{template_path.stem}.manifest.json")


def _open_presentation(template_path: Path) -> Presentation:
    try:
        return Presentation(template_path)
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Template file not found: {template_path}") from exc
    except (BadZipFile, KeyError, ValueError) as exc:
        if _looks_like_encrypted_office_file(template_path):
            raise AgentSlidesError(SCHEMA_ERROR, "password-protected files not supported") from exc
        raise AgentSlidesError(SCHEMA_ERROR, "not a valid PPTX file") from exc
    except Exception as exc:
        raise AgentSlidesError(SCHEMA_ERROR, "not a valid PPTX file") from exc


def _looks_like_encrypted_office_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(OLE_MAGIC)) == OLE_MAGIC
    except OSError:
        return False


def _build_manifest(template_path: Path, manifest_path: Path, presentation: Presentation) -> LearnResult:
    layouts_found = 0
    usable_layouts = 0
    warnings: list[str] = []
    slug_counts: dict[str, int] = {}
    masters: list[dict[str, object]] = []

    for master_index, slide_master in enumerate(presentation.slide_masters):
        layouts: list[dict[str, object]] = []
        for layout_index, slide_layout in enumerate(slide_master.slide_layouts):
            layouts_found += 1
            layout_name = slide_layout.name or f"Layout {layout_index + 1}"
            placeholders, slot_mapping, layout_warnings = _extract_layout(slide_layout, layout_name)
            warnings.extend(layout_warnings)

            slug = _unique_slug(layout_name, slug_counts)
            usable = bool(placeholders) or _is_blank_layout_name(layout_name)
            if usable:
                usable_layouts += 1

            layouts.append(
                {
                    "index": layout_index,
                    "master_index": master_index,
                    "name": layout_name,
                    "slug": slug,
                    "usable": usable,
                    "placeholders": placeholders,
                    "slot_mapping": slot_mapping,
                }
            )

        masters.append(
            {
                "index": master_index,
                "name": f"Slide Master {master_index + 1}",
                "layouts": layouts,
            }
        )

    if layouts_found == 0:
        raise AgentSlidesError(SCHEMA_ERROR, "template has no slide layouts")
    if usable_layouts == 0:
        warnings.append("template has 0 usable layouts")

    manifest = {
        "source": _relative_source_path(template_path, manifest_path),
        "source_hash": _sha256(template_path),
        "slide_masters": masters,
        "theme": _extract_theme(presentation),
    }
    _write_manifest(manifest_path, manifest)

    return LearnResult(
        manifest_path=manifest_path,
        manifest=manifest,
        layouts_found=layouts_found,
        usable_layouts=usable_layouts,
        warnings=warnings,
    )


def _extract_layout(slide_layout: object, layout_name: str) -> tuple[list[dict[str, object]], dict[str, int], list[str]]:
    placeholders: list[dict[str, object]] = []
    warnings: list[str] = []

    for placeholder in slide_layout.placeholders:
        placeholder_type = _normalize_placeholder_type(placeholder.placeholder_format.type)
        if placeholder_type is None:
            raw_type = placeholder.placeholder_format.type
            if raw_type in _WARNING_ONLY_PLACEHOLDERS:
                warnings.append(
                    f"layout '{layout_name}': skipped unsupported {raw_type.name.lower()} placeholder '{placeholder.name}'"
                )
            continue

        placeholder_record = _shape_record(
            idx=int(placeholder.placeholder_format.idx),
            type_tag=placeholder_type,
            name=placeholder.name,
            left=placeholder.left,
            top=placeholder.top,
            width=placeholder.width,
            height=placeholder.height,
            shape_id=getattr(placeholder, "shape_id", None),
            shape_kind="placeholder",
        )
        placeholders.append(placeholder_record)

    for shape in getattr(slide_layout, "shapes", []):
        if getattr(shape, "is_placeholder", False):
            continue
        extracted = _extract_non_placeholder_shape(shape)
        if extracted is not None:
            placeholders.append(extracted)

    placeholders.sort(key=lambda item: int(item["idx"]))
    return placeholders, _build_slot_mapping(placeholders), warnings


def _normalize_placeholder_type(raw_type: PP_PLACEHOLDER) -> str | None:
    return _PLACEHOLDER_TYPE_MAP.get(raw_type)


def _build_slot_mapping(placeholders: list[dict[str, object]]) -> dict[str, int]:
    slot_mapping: dict[str, int] = {}

    titles = _placeholders_of_type(placeholders, "TITLE")
    if titles:
        slot_mapping["heading"] = int(sorted(titles, key=_sort_key_by_position)[0]["idx"])

    subtitles = _placeholders_of_type(placeholders, "SUBTITLE")
    if subtitles:
        slot_mapping["subheading"] = int(sorted(subtitles, key=_sort_key_by_position)[0]["idx"])

    claimed_indexes = set(slot_mapping.values())
    suggestions = _collect_suggested_slots(placeholders)
    for slot_name in sorted(SPECIAL_SLOT_TYPES):
        suggested = suggestions.get(slot_name, [])
        if len(suggested) == 1:
            placeholder_idx = int(suggested[0]["idx"])
            slot_mapping[slot_name] = placeholder_idx
            claimed_indexes.add(placeholder_idx)

    unmapped_body_like = [
        placeholder
        for placeholder in placeholders
        if placeholder["type"] in BODY_SLOT_TYPES and int(placeholder["idx"]) not in claimed_indexes
    ]
    preferred_types = {"BODY"} if any(placeholder["type"] == "BODY" for placeholder in unmapped_body_like) else BODY_SLOT_TYPES
    bodies = sorted(
        [placeholder for placeholder in unmapped_body_like if placeholder["type"] in preferred_types],
        key=_sort_key_by_position,
    )
    if len(bodies) == 1:
        slot_mapping["body"] = int(bodies[0]["idx"])
    elif len(bodies) > 1:
        if _same_row(bodies):
            for index, placeholder in enumerate(sorted(bodies, key=_sort_key_by_x), start=1):
                slot_mapping[f"col{index}"] = int(placeholder["idx"])
        else:
            slot_mapping["body"] = int(bodies[0]["idx"])

    pictures = sorted(_placeholders_of_type(placeholders, "PICTURE"), key=_sort_key_by_position)
    if pictures:
        slot_mapping["image"] = int(pictures[0]["idx"])

    return slot_mapping


def _placeholders_of_type(placeholders: list[dict[str, object]], placeholder_type: str) -> list[dict[str, object]]:
    return [placeholder for placeholder in placeholders if placeholder["type"] == placeholder_type]


def _same_row(placeholders: list[dict[str, object]]) -> bool:
    top_values = [float(placeholder["bounds"]["y"]) for placeholder in placeholders]
    return max(top_values) - min(top_values) <= BODY_ROW_THRESHOLD_PT


def _sort_key_by_position(placeholder: dict[str, object]) -> tuple[float, float, int]:
    bounds = placeholder["bounds"]
    return float(bounds["y"]), float(bounds["x"]), int(placeholder["idx"])


def _sort_key_by_x(placeholder: dict[str, object]) -> tuple[float, int]:
    bounds = placeholder["bounds"]
    return float(bounds["x"]), int(placeholder["idx"])


def _extract_non_placeholder_shape(shape: Any) -> dict[str, object] | None:
    base = _shape_record(
        idx=_synthetic_shape_idx(getattr(shape, "shape_id", 0)),
        type_tag="UNKNOWN",
        name=getattr(shape, "name", "Shape"),
        left=getattr(shape, "left", 0),
        top=getattr(shape, "top", 0),
        width=getattr(shape, "width", 0),
        height=getattr(shape, "height", 0),
        shape_id=getattr(shape, "shape_id", None),
        shape_kind=_shape_kind(shape),
    )

    if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
        base["type"] = "GROUP"
        base["group"] = {"children": len(getattr(shape, "shapes", []))}
        base["suggested_slot"] = _suggest_slot_name(base)
        return base

    if getattr(shape, "has_table", False):
        table = shape.table
        base["type"] = "TABLE"
        base["table"] = {"rows": len(table.rows), "cols": len(table.columns)}
        base["suggested_slot"] = _suggest_slot_name(base)
        return base

    if getattr(shape, "has_chart", False):
        base["type"] = "CHART"
        base["chart"] = {"chart_type": int(shape.chart.chart_type)}
        base["suggested_slot"] = _suggest_slot_name(base)
        return base

    if getattr(shape, "has_text_frame", False) and _shape_text(shape).strip():
        base["type"] = "TEXT_BOX"
        base["text"] = _shape_text(shape)
        base["suggested_slot"] = _suggest_slot_name(base)
        return base

    return None


def _shape_record(
    *,
    idx: int,
    type_tag: str,
    name: str,
    left: int,
    top: int,
    width: int,
    height: int,
    shape_id: int | None,
    shape_kind: str,
) -> dict[str, object]:
    placeholder: dict[str, object] = {
        "idx": idx,
        "type": type_tag,
        "name": name,
        "bounds": {
            "x": _emu_to_points(left),
            "y": _emu_to_points(top),
            "w": _emu_to_points(width),
            "h": _emu_to_points(height),
        },
        "shape_kind": shape_kind,
    }
    if shape_id is not None:
        placeholder["shape_id"] = int(shape_id)
    placeholder["suggested_slot"] = _suggest_slot_name(placeholder)
    return placeholder


def _synthetic_shape_idx(shape_id: int) -> int:
    return NON_PLACEHOLDER_IDX_OFFSET + int(shape_id)


def _shape_kind(shape: Any) -> str:
    shape_type = getattr(shape, "shape_type", None)
    if shape_type is None:
        return "shape"
    name = getattr(shape_type, "name", None)
    if isinstance(name, str) and name:
        return name.casefold()
    return str(shape_type).casefold()


def _shape_text(shape: Any) -> str:
    if getattr(shape, "has_text_frame", False):
        return shape.text_frame.text
    return ""


def _collect_suggested_slots(placeholders: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    suggestions: dict[str, list[dict[str, object]]] = {}
    for placeholder in placeholders:
        slot_name = placeholder.get("suggested_slot")
        if isinstance(slot_name, str) and slot_name:
            suggestions.setdefault(slot_name, []).append(placeholder)
    return suggestions


def _suggest_slot_name(placeholder: Mapping[str, object]) -> str | None:
    placeholder_type = placeholder.get("type")
    if placeholder_type == "TITLE":
        return "heading"
    if placeholder_type == "SUBTITLE":
        return "subheading"
    if placeholder_type == "PICTURE":
        return "image"
    if placeholder_type not in BODY_SLOT_TYPES:
        return None

    role = infer_template_slot_role(str(placeholder.get("name", "")), placeholder)
    if role in {"quote", "attribution"}:
        return role
    return "body"


def _is_blank_layout_name(layout_name: str) -> bool:
    tokens = {token for token in SLUG_PATTERN.split(layout_name.casefold()) if token}
    return "blank" in tokens


def _unique_slug(layout_name: str, slug_counts: dict[str, int]) -> str:
    base_slug = _slugify(layout_name)
    count = slug_counts.get(base_slug, 0) + 1
    slug_counts[base_slug] = count
    return base_slug if count == 1 else f"{base_slug}_{count}"


def _slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("_", value.strip().lower()).strip("_")
    return slug or "layout"


def _extract_theme(presentation: Presentation) -> dict[str, object]:
    theme_root = _theme_root(presentation)
    colors = {
        "primary": _theme_color(theme_root, "accent1"),
        "secondary": _theme_color(theme_root, "accent2"),
        "accent": _theme_color(theme_root, "accent3"),
        "text": _theme_color(theme_root, "dk1"),
        "heading_text": _theme_color(theme_root, "dk2"),
        "subtle_text": _theme_color(theme_root, "lt2"),
        "background": _theme_color(theme_root, "lt1"),
    }
    fonts = {
        "heading": _theme_font(theme_root, "majorFont"),
        "body": _theme_font(theme_root, "minorFont"),
    }
    spacing = {
        "base_unit": DEFAULT_BASE_UNIT_PT,
        "margin": DEFAULT_MARGIN_PT,
        "gutter": DEFAULT_GUTTER_PT,
    }
    return {
        "colors": colors,
        "fonts": fonts,
        "spacing": spacing,
    }


def _theme_root(presentation: Presentation) -> ET.Element:
    for slide_master in presentation.slide_masters:
        for relationship in slide_master.part.rels.values():
            if relationship.reltype == THEME_RELATIONSHIP:
                return ET.fromstring(relationship.target_part.blob)
    raise AgentSlidesError(SCHEMA_ERROR, "template theme could not be read")


def _theme_color(theme_root: ET.Element, color_name: str) -> str:
    color_element = theme_root.find(f".//a:clrScheme/a:{color_name}", DRAWINGML_NS)
    if color_element is None:
        raise AgentSlidesError(SCHEMA_ERROR, f"template theme color '{color_name}' could not be read")

    srgb = color_element.find("./a:srgbClr", DRAWINGML_NS)
    if srgb is not None:
        return f"#{srgb.attrib['val']}"

    system = color_element.find("./a:sysClr", DRAWINGML_NS)
    if system is not None:
        return f"#{system.attrib.get('lastClr', system.attrib['val'])}"

    raise AgentSlidesError(SCHEMA_ERROR, f"template theme color '{color_name}' could not be read")


def _theme_font(theme_root: ET.Element, font_family: str) -> str:
    font = theme_root.find(f".//a:fontScheme/a:{font_family}/a:latin", DRAWINGML_NS)
    if font is None or "typeface" not in font.attrib:
        raise AgentSlidesError(SCHEMA_ERROR, f"template theme font '{font_family}' could not be read")
    return font.attrib["typeface"]


def _relative_source_path(template_path: Path, manifest_path: Path) -> str:
    relative_path = os.path.relpath(template_path.resolve(), manifest_path.parent.resolve())
    return Path(relative_path).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    payload = f"{json.dumps(manifest, indent=2)}\n"
    try:
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Failed to write manifest {path}: {exc.strerror or str(exc)}",
        ) from exc


def _emu_to_points(value: int) -> float:
    return round(float(value) / EMU_PER_POINT, 3)
