from __future__ import annotations

import re
from typing import Any, Mapping

_LABEL_SPLIT_PATTERN = re.compile(r"[^a-z0-9]+")
_ROLE_SIZE_VALIDATIONS = (("quote", "attribution"),)


def infer_template_slot_role(slot_name: str, slot_mapping: Mapping[str, Any]) -> str:
    explicit = slot_mapping.get("role")
    if isinstance(explicit, str) and explicit:
        return explicit.lower()

    placeholder_type = slot_mapping.get("type")
    if isinstance(placeholder_type, str) and placeholder_type.upper() == "PICTURE":
        return "image"

    for candidate in (slot_name, slot_mapping.get("name")):
        role = _role_from_label(candidate)
        if role is not None:
            return role

    return "body"


def normalize_template_slot_mapping(
    slot_mapping: Mapping[str, Any],
    *,
    placeholders_by_idx: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = dict(slot_mapping)

    for primary_role, secondary_role in _ROLE_SIZE_VALIDATIONS:
        primary_slot_names = _slots_for_role(normalized, placeholders_by_idx, primary_role)
        secondary_slot_names = _slots_for_role(normalized, placeholders_by_idx, secondary_role)
        if len(primary_slot_names) != 1 or len(secondary_slot_names) != 1:
            continue

        primary_slot = primary_slot_names[0]
        secondary_slot = secondary_slot_names[0]
        primary_area = _slot_area(normalized[primary_slot], placeholders_by_idx)
        secondary_area = _slot_area(normalized[secondary_slot], placeholders_by_idx)
        if primary_area is None or secondary_area is None:
            continue
        if primary_area < secondary_area:
            normalized[primary_slot], normalized[secondary_slot] = (
                normalized[secondary_slot],
                normalized[primary_slot],
            )

    return normalized


def _slots_for_role(
    slot_mapping: Mapping[str, Any],
    placeholders_by_idx: Mapping[int, Mapping[str, Any]],
    role: str,
) -> list[str]:
    slot_names: list[str] = []
    for slot_name, raw_slot in slot_mapping.items():
        if infer_template_slot_role(slot_name, _resolve_slot_mapping(raw_slot, placeholders_by_idx)) == role:
            slot_names.append(slot_name)
    return slot_names


def _resolve_slot_mapping(
    raw_slot: Any,
    placeholders_by_idx: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    if isinstance(raw_slot, int) and not isinstance(raw_slot, bool):
        placeholder = placeholders_by_idx.get(raw_slot)
        if placeholder is not None:
            return dict(placeholder)
        return {"idx": raw_slot}
    if isinstance(raw_slot, Mapping):
        return dict(raw_slot)
    return {}


def _slot_area(raw_slot: Any, placeholders_by_idx: Mapping[int, Mapping[str, Any]]) -> float | None:
    slot_mapping = _resolve_slot_mapping(raw_slot, placeholders_by_idx)
    bounds = slot_mapping.get("bounds", slot_mapping)
    if not isinstance(bounds, Mapping):
        return None

    width = _coerce_number(bounds.get("width", bounds.get("w")))
    height = _coerce_number(bounds.get("height", bounds.get("h")))
    if width is None or height is None:
        return None
    return width * height


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _role_from_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    lowered = value.strip().lower()
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

    tokens = {token for token in _LABEL_SPLIT_PATTERN.split(lowered) if token}
    if "quote" in tokens:
        return "quote"
    if tokens & {"attribution", "credit", "citation"}:
        return "attribution"
    if "image" in tokens or "img" in tokens:
        return "image"
    return None
