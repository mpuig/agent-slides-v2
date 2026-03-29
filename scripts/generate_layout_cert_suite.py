"""Generate deterministic certification-suite decks from template inventory and fixtures."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.types import Counters, Deck, Node, Slide

ROOT = Path(__file__).resolve().parents[1]
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
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
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be a JSON object")
    return payload


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


def _slugify(value: str) -> str:
    normalized = _SLUG_PATTERN.sub("-", value.casefold()).strip("-")
    return normalized or "template"


def _template_slug(manifest_path: Path, manifest: dict[str, Any]) -> str:
    raw_source = manifest.get("source")
    if isinstance(raw_source, dict):
        raw_source = raw_source.get("path")
    if isinstance(raw_source, str) and raw_source.strip():
        return _slugify(Path(raw_source).stem)

    stem = manifest_path.name.removesuffix(".json")
    if stem.endswith(".manifest"):
        stem = stem.removesuffix(".manifest")
    return _slugify(stem)


def _load_fixture_payloads(fixtures_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    if not fixtures_dir.is_dir():
        raise ValueError(f"Fixtures directory not found: {fixtures_dir}")

    payloads: dict[str, dict[str, dict[str, Any]]] = {}
    for fixture_path in sorted(fixtures_dir.glob("*.json")):
        fixture_payload = _load_json(fixture_path, label="Fixture")
        variants: dict[str, dict[str, Any]] = {}
        for variant_name, variant_payload in sorted(fixture_payload.items()):
            if not isinstance(variant_name, str) or not variant_name.strip():
                raise ValueError(f"Fixture variant names must be non-empty strings in {fixture_path}")
            if not isinstance(variant_payload, dict):
                raise ValueError(f"Fixture variant '{variant_name}' in {fixture_path} must be an object")
            variants[variant_name] = dict(variant_payload)
        payloads[fixture_path.stem] = variants

    if not payloads:
        raise ValueError(f"Fixtures directory does not contain any JSON fixture files: {fixtures_dir}")
    return payloads


def _iter_testable_layouts(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    raw_layouts = inventory.get("layouts")
    if not isinstance(raw_layouts, list):
        raise ValueError("Inventory field 'layouts' must be a list")

    layouts: list[dict[str, Any]] = []
    for index, raw_layout in enumerate(raw_layouts):
        if not isinstance(raw_layout, dict):
            raise ValueError(f"Inventory layouts[{index}] must be an object")
        if not bool(raw_layout.get("testable", False)):
            continue

        slug = raw_layout.get("slug")
        slot_structure = raw_layout.get("slot_structure")
        fillable_slots = raw_layout.get("fillable_slots")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"Inventory layouts[{index}] must include a non-empty slug")
        if not isinstance(slot_structure, str) or not slot_structure.strip():
            raise ValueError(f"Inventory layout '{slug}' must include a non-empty slot_structure")
        if not isinstance(fillable_slots, list) or not all(isinstance(slot, str) and slot.strip() for slot in fillable_slots):
            raise ValueError(f"Inventory layout '{slug}' fillable_slots must be a list of non-empty strings")

        layouts.append(
            {
                "slug": slug.strip(),
                "slot_structure": slot_structure.strip(),
                "fillable_slots": sorted({slot.strip() for slot in fillable_slots}, key=_slot_sort_key),
            }
        )

    if not layouts:
        raise ValueError("Inventory does not contain any testable layouts")
    return sorted(layouts, key=lambda layout: layout["slug"])


def _relative_path(target: Path, start: Path) -> str:
    return os.path.relpath(target.resolve(strict=False), start.resolve(strict=False))


def _resolve_fixture_image_path(raw_path: str, *, deck_dir: Path) -> str:
    """Copy image into deck_dir/_assets/ and return a relative path.

    Images must live inside the deck directory tree so the build command's
    path traversal guard accepts them. The copy is keyed by the full
    relative source path (not just basename) to avoid collisions when
    different fixtures reference images with the same filename from
    different directories. The copy is always refreshed to keep assets
    in sync with the current fixture set.
    """
    image_source = Path(raw_path)
    if not image_source.is_absolute():
        image_source = (ROOT / image_source).resolve(strict=False)
    if not image_source.is_file():
        raise ValueError(f"Image fixture asset not found: {raw_path}")
    import hashlib

    asset_dir = deck_dir / "_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    # Key by a hash of the full resolved path to guarantee uniqueness
    path_hash = hashlib.sha256(str(image_source).encode()).hexdigest()[:12]
    safe_name = f"{path_hash}_{image_source.name}"
    local_copy = asset_dir / safe_name
    shutil.copy2(image_source, local_copy)
    return _relative_path(local_copy, deck_dir)


def _build_nodes(
    slot_payloads: dict[str, Any],
    *,
    fillable_slots: list[str],
    deck_dir: Path,
) -> list[Node]:
    nodes: list[Node] = []
    for slot_name in fillable_slots:
        raw_payload = slot_payloads.get(slot_name)
        if raw_payload is None:
            continue
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Fixture payload for slot '{slot_name}' must be an object")

        node_id = f"n-{len(nodes) + 1}"
        if "image_path" in raw_payload:
            node = Node.model_validate(
                {
                    "node_id": node_id,
                    "slot_binding": slot_name,
                    "type": "image",
                    "content": {"blocks": []},
                    "image_fit": raw_payload.get("image_fit", "contain"),
                    "image_path": _resolve_fixture_image_path(
                        str(raw_payload["image_path"]),
                        deck_dir=deck_dir,
                    ),
                }
            )
        else:
            node = Node.model_validate(
                {
                    "node_id": node_id,
                    "slot_binding": slot_name,
                    "type": "text",
                    "content": raw_payload,
                }
            )
        nodes.append(node)
    return nodes


def _serialize_deck(deck: Deck) -> str:
    payload = deck.model_dump(mode="json", by_alias=True, exclude_none=True)
    for slide in payload["slides"]:
        slide.pop("revision", None)
        slide.pop("computed", None)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_cert_suite(
    manifest_path: Path,
    inventory: dict[str, Any],
    fixture_payloads: dict[str, dict[str, dict[str, Any]]],
    *,
    output_dir: Path,
) -> list[Path]:
    manifest = _load_json(manifest_path, label="Manifest")
    registry = TemplateLayoutRegistry(str(manifest_path))
    template_slug = _template_slug(manifest_path, manifest)
    written_paths: list[Path] = []

    for layout in _iter_testable_layouts(inventory):
        layout_slug = str(layout["slug"])
        fillable_slots = list(layout["fillable_slots"])
        slot_structure = str(layout["slot_structure"])

        registry_slots = sorted(registry.get_slot_names(layout_slug), key=_slot_sort_key)
        if registry_slots != fillable_slots:
            raise ValueError(
                f"Inventory layout '{layout_slug}' fillable_slots do not match manifest slots: "
                f"{fillable_slots} != {registry_slots}"
            )

        variants = fixture_payloads.get(slot_structure)
        if variants is None:
            raise ValueError(f"No fixture file found for slot structure '{slot_structure}'")

        for variant_name, raw_slot_payloads in sorted(variants.items()):
            deck_dir = output_dir / template_slug / layout_slug / variant_name
            nodes = _build_nodes(
                raw_slot_payloads,
                fillable_slots=fillable_slots,
                deck_dir=deck_dir,
            )
            deck = Deck(
                deck_id=f"cert-{template_slug}-{layout_slug}-{variant_name}",
                revision=0,
                theme=registry.theme.name,
                design_rules="default",
                template_manifest=_relative_path(manifest_path, deck_dir),
                slides=[Slide(slide_id="s-1", layout=layout_slug, nodes=nodes)],
                counters=Counters(slides=1, nodes=len(nodes)),
            )

            deck_path = deck_dir / "deck.json"
            deck_path.parent.mkdir(parents=True, exist_ok=True)
            deck_path.write_text(_serialize_deck(deck), encoding="utf-8")
            written_paths.append(deck_path)

    return written_paths


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        inventory = _load_json(args.inventory, label="Inventory")
        fixture_payloads = _load_fixture_payloads(args.fixtures)
        written_paths = build_cert_suite(
            args.manifest,
            inventory,
            fixture_payloads,
            output_dir=args.output,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    manifest = _load_json(args.manifest, label="Manifest")
    template_slug = _template_slug(args.manifest, manifest)
    json.dump(
        {
            "deck_count": len(written_paths),
            "fixtures_dir": str(args.fixtures),
            "inventory": str(args.inventory),
            "manifest": str(args.manifest),
            "output_dir": str(args.output),
            "template": template_slug,
        },
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
