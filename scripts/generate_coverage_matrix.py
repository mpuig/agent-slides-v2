"""Generate per-layout certification coverage from suite and run artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_slides.io import read_deck, resolve_manifest_path
from agent_slides.model.layout_provider import resolve_layout_provider
from agent_slides.render_oracle import generate_render_signals

ROOT = Path(__file__).resolve().parents[1]
_INVENTORY_FILENAMES = ("inventory.json", "layout-inventory.json")
_EXCLUDE_POLICY_FILENAMES = ("exclude-policy.json", "exclude-policy.yaml", "exclude-policy.yml")
_MIN_SIGNAL_FONT_SIZE_PT = 8.0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-dir", required=True, type=Path)
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


def _load_script_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_inventory(suite_dir: Path) -> dict[str, Any]:
    for filename in _INVENTORY_FILENAMES:
        candidate = suite_dir / filename
        if candidate.is_file():
            return _load_json(candidate, label="Inventory")

    deck_paths = sorted(suite_dir.glob("*/*/deck.json"))
    if not deck_paths:
        raise ValueError(f"Suite directory does not contain any layout variant decks: {suite_dir}")

    deck_path = deck_paths[0]
    deck = read_deck(str(deck_path))
    manifest_path = resolve_manifest_path(str(deck_path), deck)
    if manifest_path is None:
        raise ValueError(
            f"Suite inventory not found in {suite_dir} and deck {deck_path} does not reference a template manifest"
        )

    inventory_module = _load_script_module(ROOT / "scripts" / "export_layout_inventory.py", "export_layout_inventory")
    exclude_policy: dict[str, str] | None = None
    for filename in _EXCLUDE_POLICY_FILENAMES:
        candidate = suite_dir / filename
        if candidate.is_file():
            exclude_policy = inventory_module._load_exclude_policy(candidate)
            break

    manifest = _load_json(Path(manifest_path), label="Manifest")
    return inventory_module.build_inventory(manifest, exclude_policy=exclude_policy)


def _artifact_dirs(*, suite_dir: Path, output_path: Path, layout_slug: str, variant_name: str, deck_dir: Path) -> list[Path]:
    run_dir = output_path.parent
    candidates = [
        run_dir / suite_dir.name / layout_slug / variant_name,
        run_dir / layout_slug / variant_name,
        deck_dir,
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def _find_first_file(candidates: list[Path], relatives: list[str]) -> Path | None:
    for base_dir in candidates:
        for relative in relatives:
            candidate = base_dir / relative
            if candidate.is_file():
                return candidate
    return None


def _coerce_success_flag(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value > 0
    return None


def _build_success(candidates: list[Path]) -> bool:
    scores_path = _find_first_file(candidates, ["scores.json"])
    if scores_path is not None:
        payload = _load_json(scores_path, label="Scores")
        direct = _coerce_success_flag(payload.get("build_success"))
        if direct is not None:
            return direct
        nested_scores = payload.get("scores")
        if isinstance(nested_scores, dict):
            nested = _coerce_success_flag(nested_scores.get("build_success"))
            if nested is not None:
                return nested

    for base_dir in candidates:
        pptx_path = base_dir / "deck.pptx"
        if pptx_path.is_file():
            return True
        if any(base_dir.glob("*.pptx")):
            return True
    return False


def _signal_payload_from_file(path: Path, *, layout_slug: str) -> dict[str, bool]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Signals file is not valid JSON: {path}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"Signals file must contain a list: {path}")

    selected: dict[str, Any] | None = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("layout_slug") == layout_slug:
            selected = item
            break
    if selected is None and payload and isinstance(payload[0], dict):
        selected = payload[0]
    if selected is None:
        raise ValueError(f"Signals file does not contain any usable slide entries: {path}")

    raw_signals = selected.get("signals")
    if not isinstance(raw_signals, dict):
        raise ValueError(f"Signals entry must contain an object field 'signals': {path}")

    return {
        "overflow": bool(raw_signals.get("text_clipped", False)),
        "placeholder_empty": bool(raw_signals.get("placeholder_empty", False)),
        "image_missing": bool(raw_signals.get("image_missing", False)),
        "font_too_small": bool(raw_signals.get("font_too_small", False)),
    }


def _fallback_signals(deck_path: Path, *, layout_slug: str) -> dict[str, bool]:
    deck = read_deck(str(deck_path))
    provider = resolve_layout_provider(resolve_manifest_path(str(deck_path), deck))
    signals = generate_render_signals(deck, provider)

    selected: dict[str, Any] | None = None
    for item in signals:
        if item.get("layout_slug") == layout_slug:
            selected = item
            break
    if selected is None and signals:
        selected = signals[0]
    if selected is None:
        return {
            "overflow": False,
            "placeholder_empty": False,
            "image_missing": False,
            "font_too_small": False,
        }

    raw_signals = selected.get("signals", {})
    if not isinstance(raw_signals, dict):
        raw_signals = {}
    font_too_small = bool(raw_signals.get("font_too_small", False))
    if not font_too_small:
        font_too_small = any(
            computed is not None and 0.0 < computed.font_size_pt < _MIN_SIGNAL_FONT_SIZE_PT
            for slide in deck.slides
            if slide.layout == layout_slug
            for computed in slide.computed.values()
        )
    return {
        "overflow": bool(raw_signals.get("text_clipped", False)),
        "placeholder_empty": bool(raw_signals.get("placeholder_empty", False)),
        "image_missing": bool(raw_signals.get("image_missing", False)),
        "font_too_small": font_too_small,
    }


def _variant_signals(deck_path: Path, *, layout_slug: str, candidates: list[Path]) -> dict[str, bool]:
    signals_path = _find_first_file(candidates, ["signals.json", "review/signals.json"])
    if signals_path is not None:
        return _signal_payload_from_file(signals_path, layout_slug=layout_slug)
    return _fallback_signals(deck_path, layout_slug=layout_slug)


def _exclude_reason(layout: dict[str, Any]) -> str | None:
    reason = layout.get("exclude_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    if not bool(layout.get("usable", False)):
        return "layout marked unusable"
    if bool(layout.get("is_disclaimer_duplicate", False)):
        return "disclaimer duplicate"
    fillable_slots = layout.get("fillable_slots")
    if isinstance(fillable_slots, list) and not fillable_slots:
        return "no fillable slots"
    if not bool(layout.get("testable", False)):
        return "not testable"
    return None


def _failure_reasons(variant: dict[str, Any], *, image_required: bool) -> list[str]:
    reasons: list[str] = []
    if not bool(variant["build_success"]):
        reasons.append("build_failed")
    if bool(variant["overflow"]):
        reasons.append("overflow")
    if bool(variant["placeholder_empty"]):
        reasons.append("placeholder_empty")
    if image_required and bool(variant["image_missing"]):
        reasons.append("image_missing")
    if bool(variant["font_too_small"]):
        reasons.append("font_too_small")
    return reasons


def build_coverage_matrix(*, suite_dir: Path, output_path: Path) -> dict[str, Any]:
    if not suite_dir.is_dir():
        raise ValueError(f"Suite directory not found: {suite_dir}")

    inventory = _load_inventory(suite_dir)
    raw_layouts = inventory.get("layouts")
    if not isinstance(raw_layouts, list):
        raise ValueError("Inventory field 'layouts' must be a list")

    suite_variants: dict[str, dict[str, Path]] = {}
    for deck_path in sorted(suite_dir.glob("*/*/deck.json")):
        variant_name = deck_path.parent.name
        layout_slug = deck_path.parent.parent.name
        suite_variants.setdefault(layout_slug, {})[variant_name] = deck_path

    layouts_payload: list[dict[str, Any]] = []
    excluded_payload: list[dict[str, str]] = []
    passed = 0
    failed = 0
    usable = 0
    testable = 0

    for raw_layout in raw_layouts:
        if not isinstance(raw_layout, dict):
            raise ValueError("Inventory layouts must be objects")
        slug = raw_layout.get("slug")
        slot_structure = raw_layout.get("slot_structure")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("Inventory layouts must include a non-empty slug")
        if not isinstance(slot_structure, str) or not slot_structure.strip():
            raise ValueError(f"Inventory layout '{slug}' must include a non-empty slot_structure")

        if bool(raw_layout.get("usable", False)):
            usable += 1

        if not bool(raw_layout.get("testable", False)):
            reason = _exclude_reason(raw_layout)
            if reason is not None:
                excluded_payload.append({"slug": slug, "reason": reason})
            layouts_payload.append(
                {
                    "slug": slug,
                    "slot_structure": slot_structure,
                    "variants_tested": 0,
                    "variants_passed": 0,
                    "variants_failed": 0,
                    "status": "excluded",
                    "failure_reasons": [],
                    "variants": [],
                }
            )
            continue

        testable += 1
        image_required = bool(raw_layout.get("requires_image", False))
        variants_payload: list[dict[str, Any]] = []
        layout_failure_reasons: set[str] = set()
        variant_paths = suite_variants.get(slug, {})
        for variant_name, deck_path in sorted(variant_paths.items()):
            candidates = _artifact_dirs(
                suite_dir=suite_dir,
                output_path=output_path,
                layout_slug=slug,
                variant_name=variant_name,
                deck_dir=deck_path.parent,
            )
            build_success = _build_success(candidates)
            signals = _variant_signals(deck_path, layout_slug=slug, candidates=candidates)
            variant_payload = {
                "variant_name": variant_name,
                "build_success": build_success,
                "overflow": signals["overflow"],
                "placeholder_empty": signals["placeholder_empty"],
                "image_missing": signals["image_missing"],
                "font_too_small": signals["font_too_small"],
            }
            variant_payload["pass"] = bool(
                build_success
                and not variant_payload["overflow"]
                and not variant_payload["placeholder_empty"]
                and (not variant_payload["image_missing"] or not image_required)
            )
            variants_payload.append(variant_payload)
            if not variant_payload["pass"]:
                layout_failure_reasons.update(_failure_reasons(variant_payload, image_required=image_required))

        variants_passed = sum(1 for variant in variants_payload if variant["pass"])
        variants_failed = len(variants_payload) - variants_passed
        status = "pass" if variants_passed > 0 else "fail"
        if status == "pass":
            passed += 1
        else:
            failed += 1
            if not variants_payload:
                layout_failure_reasons.add("no_variants_found")

        layouts_payload.append(
            {
                "slug": slug,
                "slot_structure": slot_structure,
                "variants_tested": len(variants_payload),
                "variants_passed": variants_passed,
                "variants_failed": variants_failed,
                "status": status,
                "failure_reasons": sorted(layout_failure_reasons),
                "variants": variants_payload,
            }
        )

    coverage_pct = 100.0 if testable == 0 else round((passed / testable) * 100, 1)
    return {
        "template": suite_dir.name,
        "total_layouts": len(raw_layouts),
        "usable": usable,
        "testable": testable,
        "excluded": excluded_payload,
        "passed": passed,
        "failed": failed,
        "coverage_pct": coverage_pct,
        "run_id": output_path.parent.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layouts": layouts_payload,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        coverage = build_coverage_matrix(suite_dir=args.suite_dir, output_path=args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if coverage["coverage_pct"] == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
