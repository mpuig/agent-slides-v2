"""Generate deterministic layout-case fixtures from a layout inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGE_ASSET_PATHS = (
    "examples/images/capacity-gap-map.svg",
    "examples/images/network-coverage.svg",
    "examples/images/service-dashboard.svg",
)
_SLOT_PRIORITY = {
    "heading": 0,
    "subheading": 10,
    "body": 20,
    "quote": 30,
    "attribution": 40,
    "image": 90,
}
_COLUMN_COPY = {
    "col1": (
        "Demand hot spots",
        "Orders continue to outpace available technician hours in six fast-growth corridors.",
    ),
    "col2": (
        "Capacity bottlenecks",
        "Travel time and uneven skill mix are preventing teams from clearing the daily queue.",
    ),
    "col3": (
        "Intervention levers",
        "Leaders can restore service levels by rebalancing routing, hiring, and overtime rules.",
    ),
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Inventory file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Inventory file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Inventory root must be a JSON object")
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


def _text_block(block_type: str, text: str, *, level: int = 0) -> dict[str, Any]:
    return {"type": block_type, "text": text, "level": level}


def _text_payload(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"blocks": list(blocks)}


def _has_dense_body_slot(slots: list[str]) -> bool:
    return any(slot == "body" or _is_column_slot(slot) for slot in slots)


def _dense_body_target(slots: list[str]) -> str | None:
    for slot in slots:
        if slot == "body":
            return slot
    for slot in slots:
        if _is_column_slot(slot):
            return slot
    return None


def _is_column_slot(slot_name: str) -> bool:
    return slot_name.startswith("col") and slot_name[3:].isdigit()


def _image_payload(index: int) -> dict[str, Any]:
    return {
        "image_path": IMAGE_ASSET_PATHS[index % len(IMAGE_ASSET_PATHS)],
        "image_fit": "cover",
    }


def _heading_text(variant: str) -> str:
    if variant == "long_heading":
        return (
            "Regional demand has accelerated faster than workforce capacity, forcing "
            "leaders to rebalance coverage before service levels deteriorate further"
        )
    if variant == "narrow_safe":
        return "Stabilize priority markets"
    if variant == "image_missing":
        return "Text-only fallback keeps the storyline usable when visual assets are unavailable"
    return "Capacity gaps are concentrated in a small set of service corridors"


def _subheading_payload(variant: str) -> dict[str, Any]:
    if variant == "narrow_safe":
        return _text_payload(
            _text_block(
                "paragraph", "Focus on the six markets with the largest backlog."
            )
        )
    return _text_payload(
        _text_block(
            "paragraph",
            "The imbalance is sharpest where demand spikes collided with slower technician hiring.",
        )
    )


def _body_payload(variant: str) -> dict[str, Any]:
    if variant == "narrow_safe":
        return _text_payload(
            _text_block("paragraph", "Close the backlog before expanding coverage.")
        )
    if variant == "dense_body":
        return _text_payload(
            _text_block("heading", "Implications"),
            _text_block(
                "bullet",
                "Backlog exceeds the ten-day threshold in six priority metros.",
            ),
            _text_block(
                "bullet",
                "Travel time inflation is eroding technician utilization by roughly one shift per week.",
            ),
            _text_block(
                "bullet",
                "Attrition remains elevated where supervisors manage both dispatch and field coaching.",
            ),
            _text_block("heading", "Actions underway"),
            _text_block(
                "bullet",
                "Leadership is staging targeted hiring against the highest-margin territories first.",
            ),
            _text_block(
                "bullet",
                "Routing rules are being reset to reduce cross-district spillover.",
            ),
            _text_block(
                "bullet",
                "Weekly performance reviews now compare service-level recovery against hiring conversion.",
            ),
        )
    return _text_payload(
        _text_block(
            "paragraph",
            "Demand grew 14% year on year while field capacity expanded only 6%, leaving recurring coverage gaps in select metros.",
        ),
        _text_block(
            "bullet",
            "Eight priority markets account for most of the open service backlog.",
        ),
        _text_block(
            "bullet",
            "Utilization improves quickly when routing is reset at the district level.",
        ),
    )


def _column_payload(slot_name: str, variant: str) -> dict[str, Any]:
    heading_text, paragraph_text = _COLUMN_COPY.get(
        slot_name,
        (
            f"{slot_name.replace('_', ' ').title()} focus",
            "The workstream has a clear owner, measurable backlog, and a near-term operating target.",
        ),
    )
    if variant == "narrow_safe":
        return _text_payload(
            _text_block("heading", heading_text),
            _text_block("paragraph", "Keep the plan simple."),
        )
    if variant == "dense_body":
        return _text_payload(
            _text_block("heading", heading_text),
            _text_block(
                "bullet",
                "Revenue exposure is highest in locations with the thinnest bench.",
            ),
            _text_block(
                "bullet",
                "Supervisors are reallocating senior technicians to stabilize first-time fix rates.",
            ),
            _text_block(
                "bullet",
                "The queue length falls fastest when dispatch locks same-day overflow windows.",
            ),
            _text_block("heading", "Decision needed"),
            _text_block(
                "bullet",
                "Approve temporary overtime in districts that already have qualified labor.",
            ),
            _text_block(
                "bullet",
                "Sequence new hiring after route redesign to avoid absorbing avoidable cost.",
            ),
        )
    return _text_payload(
        _text_block("heading", heading_text), _text_block("paragraph", paragraph_text)
    )


def _quote_payload(variant: str) -> dict[str, Any]:
    if variant == "narrow_safe":
        return _text_payload(
            _text_block(
                "paragraph",
                "Capacity followed the old footprint, not the new demand map.",
            )
        )
    return _text_payload(
        _text_block(
            "paragraph",
            "We do not have a national staffing issue; we have a regional planning issue that looks national in aggregate.",
        )
    )


def _attribution_payload() -> dict[str, Any]:
    return _text_payload(_text_block("paragraph", "Chief Operating Officer"))


def _default_payload(slot_name: str, variant: str) -> dict[str, Any]:
    if variant == "narrow_safe":
        return _text_payload(
            _text_block(
                "paragraph", f"{slot_name.replace('_', ' ').title()} stays concise."
            )
        )
    return _text_payload(
        _text_block(
            "paragraph",
            f"{slot_name.replace('_', ' ').title()} reinforces the operating case with a short, concrete point.",
        )
    )


def _slot_payload(
    slot_name: str, variant: str, *, dense_target: str | None
) -> dict[str, Any] | None:
    if slot_name == "image":
        if variant == "image_missing":
            return None
        image_index = 1 if variant == "image_present" else 0
        return _image_payload(image_index)
    if slot_name == "heading":
        return _text_payload(_text_block("heading", _heading_text(variant)))
    if slot_name == "subheading":
        return _subheading_payload(variant)
    if slot_name == "body":
        body_variant = (
            "dense_body"
            if dense_target == slot_name and variant == "dense_body"
            else variant
        )
        return _body_payload(body_variant)
    if _is_column_slot(slot_name):
        column_variant = (
            "dense_body"
            if dense_target == slot_name and variant == "dense_body"
            else variant
        )
        return _column_payload(slot_name, column_variant)
    if slot_name == "quote":
        return _quote_payload(variant)
    if slot_name == "attribution":
        return _attribution_payload()
    return _default_payload(slot_name, variant)


def _build_variant(slots: list[str], variant: str) -> dict[str, Any]:
    dense_target = _dense_body_target(slots) if variant == "dense_body" else None
    payload: dict[str, Any] = {}
    for slot_name in slots:
        slot_payload = _slot_payload(slot_name, variant, dense_target=dense_target)
        if slot_payload is not None:
            payload[slot_name] = slot_payload
    return payload


def _collect_slot_structures(inventory: dict[str, Any]) -> dict[str, list[str]]:
    layouts = inventory.get("layouts")
    if not isinstance(layouts, list):
        raise ValueError("Inventory field 'layouts' must be a list")

    structures: dict[str, set[str]] = {}
    for layout in layouts:
        if not isinstance(layout, dict):
            raise ValueError("Inventory layouts must be objects")
        if not bool(layout.get("testable", False)):
            continue

        slot_structure = layout.get("slot_structure")
        if not isinstance(slot_structure, str) or not slot_structure.strip():
            raise ValueError(
                "Testable layouts must include a non-empty 'slot_structure'"
            )
        fillable_slots = layout.get("fillable_slots")
        if not isinstance(fillable_slots, list) or not all(
            isinstance(slot, str) for slot in fillable_slots
        ):
            raise ValueError(
                f"Layout '{layout.get('slug', '<unknown>')}' fillable_slots must be a list of strings"
            )

        structures.setdefault(slot_structure, set()).update(fillable_slots)

    if not structures:
        raise ValueError("Inventory does not contain any testable layouts")

    return {
        key: sorted(values, key=_slot_sort_key)
        for key, values in sorted(structures.items())
    }


def build_fixture_payloads(
    inventory: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    for asset_path in IMAGE_ASSET_PATHS:
        if not (ROOT / asset_path).is_file():
            raise ValueError(f"Image fixture asset not found: {asset_path}")

    structures = _collect_slot_structures(inventory)
    payloads: dict[str, dict[str, dict[str, Any]]] = {}
    for slot_structure, slots in structures.items():
        if slot_structure == "blank":
            payloads[slot_structure] = {"blank": {}}
            continue
        variants = {
            "nominal": _build_variant(slots, "nominal"),
            "narrow_safe": _build_variant(slots, "narrow_safe"),
        }
        if "heading" in slots:
            variants["long_heading"] = _build_variant(slots, "long_heading")
        if _has_dense_body_slot(slots):
            variants["dense_body"] = _build_variant(slots, "dense_body")
        if "image" in slots:
            variants["image_present"] = _build_variant(slots, "image_present")
            variants["image_missing"] = _build_variant(slots, "image_missing")
        payloads[slot_structure] = variants
    return payloads


def write_fixture_payloads(
    payloads: dict[str, dict[str, dict[str, Any]]], output_dir: Path
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for slot_structure, payload in payloads.items():
        path = output_dir / f"{slot_structure}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written_paths.append(path)
    return written_paths


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        inventory = _load_json(args.inventory)
        payloads = build_fixture_payloads(inventory)
        written_paths = write_fixture_payloads(payloads, args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    json.dump(
        {
            "inventory": str(args.inventory),
            "output_dir": str(args.output),
            "slot_structure_count": len(written_paths),
            "written_files": [path.name for path in written_paths],
        },
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
