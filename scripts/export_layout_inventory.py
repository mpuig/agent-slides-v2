"""Export a deterministic layout inventory from a learned manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a project dependency.
    yaml = None

SLOT_STRUCTURE_VALUES = {
    "heading_only",
    "heading_body",
    "heading_image",
    "heading_body_image",
    "multi_slot",
    "blank",
}
_SLOT_PRIORITY = {
    "heading": 0,
    "subheading": 10,
    "body": 20,
    "quote": 30,
    "attribution": 40,
    "image": 90,
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path", type=Path)
    parser.add_argument("--exclude-policy", type=Path, default=None)
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Manifest file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Manifest root must be a JSON object")
    return payload


def _load_exclude_policy(
    path: Path | None,
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> dict[str, str]:
    resolved_path = _resolve_exclude_policy_path(path, manifest=manifest, manifest_path=manifest_path)
    if resolved_path is None:
        return {}

    try:
        raw_text = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Exclude policy file not found: {resolved_path}") from exc

    if resolved_path.suffix.casefold() in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover
            raise ValueError("PyYAML is required to read YAML exclude policies")
        loaded = yaml.safe_load(raw_text)
    else:
        try:
            loaded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Exclude policy file is not valid JSON: {resolved_path}") from exc

    if loaded is None:
        return {}

    if isinstance(loaded, list):
        return _load_policy_entries(loaded)
    if not isinstance(loaded, dict):
        raise ValueError("Exclude policy root must be an array or object")

    candidate = loaded.get("layouts")
    if candidate is None:
        candidate = loaded.get("exclude_layouts")
    if candidate is None:
        candidate = loaded
    if isinstance(candidate, list):
        return _load_policy_entries(candidate)
    if not isinstance(candidate, dict):
        raise ValueError("Exclude policy layout entries must be an array or object")

    policy: dict[str, str] = {}
    for slug, raw_reason in candidate.items():
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("Exclude policy slugs must be non-empty strings")
        reason = _normalize_exclude_reason(raw_reason, slug=slug)
        if reason is not None:
            policy[slug.strip()] = reason
    return policy


def _resolve_exclude_policy_path(
    path: Path | None,
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> Path | None:
    if path is None:
        return None
    if path.is_dir():
        template_name = _template_name_for_policy(manifest, manifest_path)
        candidate = path / f"{template_name}.json"
        return candidate if candidate.exists() else None
    if path.exists():
        return path
    raise ValueError(f"Exclude policy path not found: {path}")


def _template_name_for_policy(manifest: dict[str, Any], manifest_path: Path) -> str:
    raw_source = manifest.get("source")
    if isinstance(raw_source, str) and raw_source.strip():
        return Path(raw_source).stem

    name = manifest_path.name
    if name.endswith(".manifest.json"):
        return name[: -len(".manifest.json")]
    if manifest_path.suffix:
        return manifest_path.stem
    return name


def _load_policy_entries(entries: list[object]) -> dict[str, str]:
    policy: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Exclude policy entry {index} must be an object")
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"Exclude policy entry {index} must include a non-empty 'slug'")
        reason = _normalize_exclude_reason(entry, slug=slug)
        if reason is None:
            raise ValueError(f"Exclude policy entry '{slug}' must include a non-empty 'reason'")
        policy[slug.strip()] = reason
    return policy


def _normalize_exclude_reason(raw_reason: object, *, slug: str) -> str | None:
    if raw_reason is None:
        return None
    if isinstance(raw_reason, str):
        normalized = raw_reason.strip()
        return normalized or None
    if isinstance(raw_reason, dict):
        reason = raw_reason.get("exclude_reason", raw_reason.get("reason"))
        if reason is None:
            return None
        if not isinstance(reason, str):
            raise ValueError(f"Exclude reason for '{slug}' must be a string")
        normalized = reason.strip()
        return normalized or None
    raise ValueError(f"Exclude policy entry for '{slug}' must be a string, object, or null")


def _iter_layouts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if "slide_masters" in manifest:
        slide_masters = manifest["slide_masters"]
        if not isinstance(slide_masters, list):
            raise ValueError("Manifest field 'slide_masters' must be a list")
        layouts: list[dict[str, Any]] = []
        for master_index, master in enumerate(slide_masters):
            if not isinstance(master, dict):
                raise ValueError(f"Manifest slide_masters[{master_index}] must be an object")
            master_layouts = master.get("layouts", [])
            if not isinstance(master_layouts, list):
                raise ValueError(f"Manifest slide_masters[{master_index}].layouts must be a list")
            for layout in master_layouts:
                if not isinstance(layout, dict):
                    raise ValueError("Manifest layouts must be objects")
                layouts.append(layout)
        return layouts

    layouts = manifest.get("layouts")
    if isinstance(layouts, list):
        if not all(isinstance(layout, dict) for layout in layouts):
            raise ValueError("Manifest layouts must be objects")
        return list(layouts)

    raise ValueError("Manifest must contain 'slide_masters' or 'layouts'")


def _slot_sort_key(slot_name: str) -> tuple[int, str]:
    if slot_name in _SLOT_PRIORITY:
        return (_SLOT_PRIORITY[slot_name], slot_name)
    if slot_name.startswith("col") and slot_name[3:].isdigit():
        return (50 + int(slot_name[3:]), slot_name)
    if "_" in slot_name:
        prefix, _, suffix = slot_name.rpartition("_")
        if suffix.isdigit():
            return (70, f"{prefix}:{int(suffix):06d}")
    return (80, slot_name)


def _normalize_bounds(raw_bounds: object, *, context: str) -> dict[str, float]:
    if not isinstance(raw_bounds, dict):
        raise ValueError(f"{context} must be an object")

    x = raw_bounds.get("x", raw_bounds.get("left"))
    y = raw_bounds.get("y", raw_bounds.get("top"))
    w = raw_bounds.get("w", raw_bounds.get("width"))
    h = raw_bounds.get("h", raw_bounds.get("height"))

    normalized: dict[str, float] = {}
    for key, raw_value in {"x": x, "y": y, "w": w, "h": h}.items():
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ValueError(f"{context}.{key} must be numeric")
        normalized[key] = float(raw_value)
    return normalized


def _placeholders_by_idx(layout: dict[str, Any]) -> dict[int, dict[str, float]]:
    placeholders = layout.get("placeholders", [])
    if placeholders is None:
        return {}
    if not isinstance(placeholders, list):
        raise ValueError(f"Layout '{layout.get('slug', '<unknown>')}' placeholders must be a list")

    resolved: dict[int, dict[str, float]] = {}
    for placeholder in placeholders:
        if not isinstance(placeholder, dict):
            raise ValueError("Layout placeholders must be objects")
        idx = placeholder.get("idx")
        if isinstance(idx, bool) or not isinstance(idx, int):
            raise ValueError("Layout placeholder idx must be an integer")
        resolved[idx] = _normalize_bounds(
            placeholder.get("bounds", placeholder),
            context=f"layout '{layout.get('slug', '<unknown>')}' placeholder[{idx}] bounds",
        )
    return resolved


def _resolve_slot_bounds(slot_name: str, raw_slot: object, *, placeholders_by_idx: dict[int, dict[str, float]]) -> dict[str, float]:
    if isinstance(raw_slot, bool):
        raise ValueError(f"slot_mapping[{slot_name!r}] must not be a boolean")
    if isinstance(raw_slot, int):
        try:
            return dict(placeholders_by_idx[raw_slot])
        except KeyError as exc:
            raise ValueError(f"slot_mapping[{slot_name!r}] references missing placeholder idx {raw_slot}") from exc
    if not isinstance(raw_slot, dict):
        raise ValueError(f"slot_mapping[{slot_name!r}] must be an integer or object")
    return _normalize_bounds(raw_slot.get("bounds", raw_slot), context=f"slot_mapping[{slot_name!r}] bounds")


def _classify_slot_structure(fillable_slots: list[str]) -> str:
    slot_names = set(fillable_slots)
    if not slot_names:
        return "blank"

    if "heading" in slot_names and slot_names.issubset({"heading", "subheading"}):
        return "heading_only"
    if {"heading", "body"}.issubset(slot_names) and slot_names.issubset({"heading", "subheading", "body"}):
        return "heading_body"
    if {"heading", "image"}.issubset(slot_names) and slot_names.issubset({"heading", "subheading", "image"}):
        return "heading_image"
    if {"heading", "body", "image"}.issubset(slot_names) and slot_names.issubset(
        {"heading", "subheading", "body", "image"}
    ):
        return "heading_body_image"
    return "multi_slot"


def _is_testable(
    *,
    usable: bool,
    exclude_reason: str | None,
) -> bool:
    if not usable:
        return False
    if exclude_reason is not None:
        return False
    return True


def build_inventory(manifest: dict[str, Any], *, exclude_policy: dict[str, str] | None = None) -> dict[str, Any]:
    policy = exclude_policy or {}
    layouts = _iter_layouts(manifest)
    entries: list[dict[str, Any]] = []

    for layout in layouts:
        slug = layout.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("Every layout must include a non-empty 'slug'")
        slot_mapping = layout.get("slot_mapping", {})
        if not isinstance(slot_mapping, dict):
            raise ValueError(f"Layout '{slug}' slot_mapping must be an object")

        fillable_slots = sorted((str(slot_name) for slot_name in slot_mapping), key=_slot_sort_key)
        placeholder_idx_map = _placeholders_by_idx(layout)
        placeholder_bounds = {
            slot_name: _resolve_slot_bounds(slot_name, slot_mapping[slot_name], placeholders_by_idx=placeholder_idx_map)
            for slot_name in fillable_slots
        }
        usable = bool(layout.get("usable", bool(fillable_slots)))
        exclude_reason = policy.get(slug)
        is_disclaimer_duplicate = slug.startswith("d_")

        entry = {
            "slug": slug,
            "usable": usable,
            "requires_image": "image" in slot_mapping,
            "is_disclaimer_duplicate": is_disclaimer_duplicate,
            "slot_structure": _classify_slot_structure(fillable_slots),
            "fillable_slots": fillable_slots,
            "placeholder_bounds": placeholder_bounds,
            "testable": _is_testable(
                usable=usable,
                exclude_reason=exclude_reason,
            ),
            "exclude_reason": exclude_reason,
        }
        if entry["slot_structure"] not in SLOT_STRUCTURE_VALUES:
            raise ValueError(f"Unsupported slot structure generated for '{slug}'")
        entries.append(entry)

    entries.sort(key=lambda entry: str(entry["slug"]))
    return {
        "source": manifest.get("source"),
        "source_hash": manifest.get("source_hash"),
        "layout_count": len(entries),
        "testable_count": sum(1 for entry in entries if entry["testable"]),
        "layouts": entries,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = _load_json(args.manifest_path)
        exclude_policy = _load_exclude_policy(
            args.exclude_policy,
            manifest=manifest,
            manifest_path=args.manifest_path,
        )
        inventory = build_inventory(manifest, exclude_policy=exclude_policy)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    json.dump(inventory, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
