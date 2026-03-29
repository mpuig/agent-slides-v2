"""Generate per-layout coverage results from certification artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON file is not valid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_inventory(suite_dir: Path) -> dict[str, Any]:
    for candidate_name in ("layout-inventory.json", "inventory.json"):
        candidate = suite_dir / candidate_name
        if candidate.exists():
            return _load_json(candidate)
    raise ValueError(f"Inventory file not found under {suite_dir}")


def _variant_failure_reasons(variant: dict[str, Any], *, requires_image: bool) -> list[str]:
    reasons: list[str] = []
    if not variant["build_success"]:
        reasons.append("build failed")
    if variant["overflow"]:
        reasons.append("overflow")
    if variant["placeholder_empty"]:
        reasons.append("placeholder empty")
    if requires_image and variant["image_missing"]:
        reasons.append("image missing")
    if variant["font_too_small"]:
        reasons.append("font too small")
    return reasons


def _normalize_variant_result(raw_variant: dict[str, Any], *, path: Path, requires_image: bool) -> dict[str, Any]:
    signals = raw_variant.get("signals", {})
    if not isinstance(signals, dict):
        raise ValueError(f"Variant signals must be an object: {path}")

    variant_name = raw_variant.get("variant_name", path.stem)
    if not isinstance(variant_name, str) or not variant_name.strip():
        raise ValueError(f"Variant name must be a non-empty string: {path}")

    def _bool_field(name: str, *, fallback: str | None = None) -> bool:
        raw_value = raw_variant.get(name, signals.get(name))
        if raw_value is None and fallback is not None:
            raw_value = raw_variant.get(fallback, signals.get(fallback))
        if raw_value is None:
            return False
        if not isinstance(raw_value, bool):
            raise ValueError(f"Variant field '{name}' must be a boolean: {path}")
        return raw_value

    normalized = {
        "variant_name": variant_name.strip(),
        "build_success": _bool_field("build_success"),
        "overflow": _bool_field("overflow", fallback="text_clipped"),
        "placeholder_empty": _bool_field("placeholder_empty"),
        "image_missing": _bool_field("image_missing"),
        "font_too_small": _bool_field("font_too_small"),
    }
    normalized["pass"] = (
        normalized["build_success"]
        and not normalized["overflow"]
        and not normalized["placeholder_empty"]
        and (not normalized["image_missing"] or not requires_image)
    )
    return normalized


def _load_variant_results(suite_dir: Path, *, inventory_by_slug: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    results_root = suite_dir / "results"
    if not results_root.exists():
        return {}

    variants_by_layout: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(results_root.rglob("*.json")):
        raw_variant = _load_json(path)
        raw_layout_slug = raw_variant.get("layout_slug", path.parent.name)
        if not isinstance(raw_layout_slug, str) or not raw_layout_slug.strip():
            raise ValueError(f"Variant result missing non-empty layout_slug: {path}")
        layout_slug = raw_layout_slug.strip()
        layout = inventory_by_slug.get(layout_slug)
        if layout is None:
            raise ValueError(f"Variant result references unknown layout '{layout_slug}': {path}")
        variants_by_layout.setdefault(layout_slug, []).append(
            _normalize_variant_result(raw_variant, path=path, requires_image=bool(layout.get("requires_image", False)))
        )
    return variants_by_layout


def build_coverage_matrix(
    inventory: dict[str, Any],
    *,
    suite_dir: Path,
    output_path: Path,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    raw_layouts = inventory.get("layouts")
    if not isinstance(raw_layouts, list):
        raise ValueError("Inventory field 'layouts' must be a list")

    layouts = [layout for layout in raw_layouts if isinstance(layout, dict)]
    if len(layouts) != len(raw_layouts):
        raise ValueError("Inventory layouts must be objects")

    inventory_by_slug: dict[str, dict[str, Any]] = {}
    for layout in layouts:
        slug = layout.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("Inventory layouts must include a non-empty 'slug'")
        inventory_by_slug[slug] = layout

    variants_by_layout = _load_variant_results(suite_dir, inventory_by_slug=inventory_by_slug)
    evaluated_at = timestamp or datetime.now(timezone.utc)
    entries: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    passed_count = 0
    failed_count = 0

    for layout in sorted(layouts, key=lambda item: str(item["slug"])):
        slug = str(layout["slug"])
        exclude_reason = layout.get("exclude_reason")
        if exclude_reason is not None and not isinstance(exclude_reason, str):
            raise ValueError(f"Layout '{slug}' exclude_reason must be a string or null")

        variants = variants_by_layout.get(slug, [])
        variants_passed = sum(1 for variant in variants if variant["pass"])
        variants_failed = len(variants) - variants_passed

        if exclude_reason:
            status = "excluded"
            failure_reasons: list[str] = []
            excluded.append({"slug": slug, "reason": exclude_reason})
        else:
            failure_reason_set: set[str] = set()
            for variant in variants:
                failure_reason_set.update(
                    _variant_failure_reasons(variant, requires_image=bool(layout.get("requires_image", False)))
                )
            if bool(layout.get("testable", False)) and not variants:
                failure_reason_set.add("no variants evaluated")
            status = "pass" if bool(layout.get("testable", False)) and variants_passed > 0 else "fail"
            failure_reasons = sorted(failure_reason_set)
            if bool(layout.get("testable", False)):
                if status == "pass":
                    passed_count += 1
                else:
                    failed_count += 1

        entries.append(
            {
                "slug": slug,
                "slot_structure": layout.get("slot_structure"),
                "variants_tested": len(variants),
                "variants_passed": variants_passed,
                "variants_failed": variants_failed,
                "status": status,
                "failure_reasons": failure_reasons,
                "variants": variants,
            }
        )

    testable_count = sum(1 for layout in layouts if bool(layout.get("testable", False)))
    coverage_pct = 100.0 if testable_count == 0 else round((passed_count / testable_count) * 100, 1)
    return {
        "template": suite_dir.name,
        "total_layouts": len(layouts),
        "usable": sum(1 for layout in layouts if bool(layout.get("usable", False))),
        "testable": testable_count,
        "excluded": excluded,
        "passed": passed_count,
        "failed": failed_count,
        "coverage_pct": coverage_pct,
        "run_id": output_path.parent.name,
        "timestamp": evaluated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "layouts": entries,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        inventory = _load_inventory(args.suite_dir)
        matrix = build_coverage_matrix(inventory, suite_dir=args.suite_dir, output_path=args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.dump(matrix, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if matrix["coverage_pct"] == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
