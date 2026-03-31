"""Inspect command for summarizing learned template manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.types import SlotDef


def _slot_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
    slot_name, placeholder_idx = item
    if isinstance(placeholder_idx, int):
        return (placeholder_idx, slot_name)
    return (10**9, slot_name)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(
            FILE_NOT_FOUND, f"Manifest file not found: {path}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR, f"Manifest file is not valid JSON: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest root must be a JSON object.")

    return payload


def _width_class(width_pt: float) -> str:
    if width_pt <= 210:
        return "very_narrow"
    if width_pt <= 290:
        return "narrow"
    if width_pt <= 400:
        return "medium_narrow"
    if width_pt <= 600:
        return "medium"
    if width_pt <= 800:
        return "wide"
    return "full"


def _max_heading_words(width_pt: float) -> int:
    if width_pt <= 210:
        return 3
    if width_pt <= 290:
        return 5
    if width_pt <= 400:
        return 8
    if width_pt <= 600:
        return 10
    if width_pt <= 800:
        return 12
    return 12


def _body_density(body_area_pt2: float) -> str:
    if body_area_pt2 >= 200_000:
        return "dense"
    if body_area_pt2 >= 80_000:
        return "medium"
    if body_area_pt2 >= 30_000:
        return "light"
    return "minimal"


def _body_max_bullets(body_area_pt2: float) -> int:
    if body_area_pt2 >= 200_000:
        return 6
    if body_area_pt2 >= 80_000:
        return 4
    if body_area_pt2 >= 30_000:
        return 3
    return 2


def _slot_summary(slot: SlotDef) -> dict[str, Any]:
    summary: dict[str, Any] = {"role": slot.role}
    if slot.width is not None:
        summary["width_pt"] = round(float(slot.width), 1)
    if slot.height is not None:
        summary["height_pt"] = round(float(slot.height), 1)
    if slot.text_color is not None:
        summary["text_color"] = slot.text_color
    if slot.bg_color is not None:
        summary["bg_color"] = slot.bg_color
    return summary


def _summarize_layout_rich(
    slug: str, registry: TemplateLayoutRegistry
) -> dict[str, Any]:
    layout_def = registry.get_layout(slug)
    slot_names = registry.get_slot_names(slug)

    heading_slot = layout_def.slots.get("heading")
    body_slot = layout_def.slots.get("body")

    heading_width = (
        float(heading_slot.width) if heading_slot and heading_slot.width else 0
    )
    heading_height = (
        float(heading_slot.height) if heading_slot and heading_slot.height else 0
    )

    has_body = "body" in slot_names

    body_area = 0.0
    if body_slot and body_slot.width and body_slot.height:
        body_area = float(body_slot.width) * float(body_slot.height)

    summary: dict[str, Any] = {
        "slug": slug,
        "slots": slot_names,
        "heading_width_pt": round(heading_width, 1),
        "heading_height_pt": round(heading_height, 1),
        "width_class": _width_class(heading_width) if heading_width > 0 else "unknown",
        "max_heading_words": _max_heading_words(heading_width)
        if heading_width > 0
        else 10,
        "has_body": has_body,
        "has_image": "image" in slot_names,
    }

    if has_body and body_slot:
        summary["body_density"] = _body_density(body_area)
        summary["body_max_bullets"] = _body_max_bullets(body_area)

    if heading_slot and heading_slot.text_color:
        summary["heading_text_color"] = heading_slot.text_color
    if heading_slot and heading_slot.bg_color:
        summary["bg_color"] = heading_slot.bg_color

    return summary


def summarize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize manifest using raw JSON (legacy path)."""
    source = payload.get("source", "")
    if not isinstance(source, str):
        source = str(source)

    slide_masters = payload.get("slide_masters", [])
    if not isinstance(slide_masters, list):
        raise AgentSlidesError(
            SCHEMA_ERROR, "Manifest field 'slide_masters' must be an array."
        )

    layouts: list[dict[str, Any]] = []
    for index, master in enumerate(slide_masters):
        if not isinstance(master, dict):
            raise AgentSlidesError(
                SCHEMA_ERROR, f"Manifest slide_masters[{index}] must be an object."
            )
        master_layouts = master.get("layouts", [])
        if not isinstance(master_layouts, list):
            raise AgentSlidesError(
                SCHEMA_ERROR,
                f"Manifest slide_masters[{index}].layouts must be an array.",
            )
        for layout_index, layout in enumerate(master_layouts):
            if not isinstance(layout, dict):
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest slide_masters[{index}].layouts[{layout_index}] must be an object.",
                )
            name = layout.get("name", f"Layout {layout_index + 1}")
            slug = layout.get("slug", name)
            slot_mapping = layout.get("slot_mapping", {})
            if isinstance(slot_mapping, dict):
                slot_items = sorted(slot_mapping.items(), key=_slot_sort_key)
                slots = [s for s, _ in slot_items]
            else:
                slots = []
            usable = bool(slots) or str(name).casefold() == "blank"
            entry: dict[str, Any] = {
                "name": str(name),
                "slug": str(slug),
                "slots": slots,
                "usable": usable,
            }
            if not usable:
                entry["reason"] = "no typed placeholders"
            layouts.append(entry)

    theme = payload.get("theme")
    return {
        "ok": True,
        "data": {
            "source": source,
            "layouts_found": len(layouts),
            "usable_layouts": sum(1 for layout in layouts if layout.get("usable")),
            "theme_extracted": isinstance(theme, dict) and bool(theme),
            "layouts": layouts,
        },
    }


def summarize_manifest_rich(
    manifest_path: Path,
) -> dict[str, Any]:
    """Summarize manifest using TemplateLayoutRegistry for full slot details."""
    registry = TemplateLayoutRegistry(manifest_path)
    slugs = registry.list_layouts()

    layouts = [_summarize_layout_rich(slug, registry) for slug in slugs]
    theme = registry.theme

    theme_info: dict[str, Any] = {}
    if theme:
        theme_info = {
            "fonts": {
                "heading": theme.fonts.heading,
                "body": theme.fonts.body,
            },
            "colors": {
                "primary": theme.colors.primary,
                "background": theme.colors.background,
                "text": theme.colors.text,
                "heading_text": theme.colors.heading_text,
            },
        }

    # Categorize layouts for quick reference
    categories: dict[str, list[str]] = {
        "full_width_with_body": [],
        "medium_with_body": [],
        "narrow_with_body": [],
        "heading_only": [],
        "image_layouts": [],
    }
    for layout in layouts:
        slug = layout["slug"]
        wc = layout.get("width_class", "")
        has_body = layout.get("has_body", False)
        has_image = layout.get("has_image", False)

        if has_image:
            categories["image_layouts"].append(slug)
        elif not has_body:
            categories["heading_only"].append(slug)
        elif wc in ("full", "wide"):
            categories["full_width_with_body"].append(slug)
        elif wc in ("medium", "medium_narrow"):
            categories["medium_with_body"].append(slug)
        else:
            categories["narrow_with_body"].append(slug)

    manifest = _read_manifest(manifest_path)
    relative_source = manifest.get("source", str(registry.source_path))

    return {
        "ok": True,
        "data": {
            "source": str(relative_source),
            "layouts_found": len(layouts),
            "usable_layouts": len(layouts),
            "theme": theme_info,
            "categories": categories,
            "layouts": layouts,
        },
    }


@click.command("inspect")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
def inspect_command(path: Path) -> None:
    """Summarize a learned template manifest."""

    try:
        result = summarize_manifest_rich(path)
    except Exception:
        manifest = _read_manifest(path)
        result = summarize_manifest(manifest)
    click.echo(json.dumps(result))
