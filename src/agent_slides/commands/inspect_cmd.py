"""Inspect command for summarizing learned template manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Manifest file not found: {path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest file is not valid JSON: {path}") from exc

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


def _summarize_layout(layout: dict[str, Any]) -> dict[str, Any]:
    name = _require_string(layout, "name")
    slug = _require_string(layout, "slug")
    slot_mapping = _require_dict(layout, "slot_mapping")
    slots = [slot_name for slot_name, _ in sorted(slot_mapping.items(), key=_slot_sort_key)]
    usable = bool(slots) or name.casefold() == "blank"

    summary: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "slots": slots,
        "usable": usable,
    }
    if not usable:
        summary["reason"] = "no typed placeholders"
    return summary


def summarize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    source = _require_string(payload, "source")
    slide_masters = _require_list(payload, "slide_masters")

    layouts: list[dict[str, Any]] = []
    for index, master in enumerate(slide_masters):
        if not isinstance(master, dict):
            raise AgentSlidesError(SCHEMA_ERROR, f"Manifest slide_masters[{index}] must be an object.")
        for layout_index, layout in enumerate(_require_list(master, "layouts")):
            if not isinstance(layout, dict):
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest slide_masters[{index}].layouts[{layout_index}] must be an object.",
                )
            layouts.append(_summarize_layout(layout))

    theme = payload.get("theme")
    return {
        "ok": True,
        "data": {
            "source": source,
            "layouts_found": len(layouts),
            "usable_layouts": sum(1 for layout in layouts if layout["usable"]),
            "theme_extracted": isinstance(theme, dict) and bool(theme),
            "layouts": layouts,
        },
    }


@click.command("inspect")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
def inspect_command(path: Path) -> None:
    """Summarize a learned template manifest."""

    manifest = _read_manifest(path)
    click.echo(json.dumps(summarize_manifest(manifest)))
