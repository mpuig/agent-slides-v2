#!/usr/bin/env python3
"""Compare per-layout coverage between two coverage.json runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_coverage(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Coverage payload must be a JSON object: {path}")
    return payload


def _layouts_by_slug(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layouts = coverage.get("layouts", [])
    if not isinstance(layouts, list):
        raise ValueError("Coverage payload must include a list-valued 'layouts' field")

    by_slug: dict[str, dict[str, Any]] = {}
    for layout in layouts:
        if not isinstance(layout, dict):
            raise ValueError("Coverage layouts must be JSON objects")
        slug = layout.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError("Coverage layouts must include a non-empty 'slug'")
        by_slug[slug] = layout
    return by_slug


def _variants_passed(layout: dict[str, Any]) -> int:
    value = layout.get("variants_passed", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Coverage layouts must include integer 'variants_passed' values")
    return value


def compare_coverage_payloads(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_template = before.get("template")
    after_template = after.get("template")
    if isinstance(before_template, str) and isinstance(after_template, str) and before_template != after_template:
        raise ValueError(
            f"Coverage templates do not match: before={before_template!r}, after={after_template!r}"
        )

    before_layouts = _layouts_by_slug(before)
    after_layouts = _layouts_by_slug(after)

    regressions: list[dict[str, int | str]] = []
    improvements: list[dict[str, int | str]] = []
    unchanged: list[dict[str, int | str]] = []
    new_layouts: list[dict[str, int | str]] = []

    for slug in sorted(after_layouts):
        after_passed = _variants_passed(after_layouts[slug])
        before_layout = before_layouts.get(slug)
        if before_layout is None:
            new_layouts.append({"slug": slug, "before_passed": 0, "after_passed": after_passed})
            continue

        before_passed = _variants_passed(before_layout)
        entry = {"slug": slug, "before_passed": before_passed, "after_passed": after_passed}
        if after_passed < before_passed:
            regressions.append(entry)
        elif after_passed > before_passed:
            improvements.append(entry)
        else:
            unchanged.append(entry)

    for slug in sorted(set(before_layouts) - set(after_layouts)):
        before_passed = _variants_passed(before_layouts[slug])
        entry = {"slug": slug, "before_passed": before_passed, "after_passed": 0}
        if before_passed > 0:
            regressions.append(entry)
        else:
            unchanged.append(entry)

    def _sort_entries(entries: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
        return sorted(entries, key=lambda entry: str(entry["slug"]))

    return {
        "template": after_template if isinstance(after_template, str) else before_template,
        "regressions": _sort_entries(regressions),
        "improvements": _sort_entries(improvements),
        "unchanged": _sort_entries(unchanged),
        "new_layouts": _sort_entries(new_layouts),
    }


def compare_coverage_files(*, before_path: Path, after_path: Path) -> dict[str, Any]:
    return compare_coverage_payloads(_load_coverage(before_path), _load_coverage(after_path))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare per-layout coverage between two runs")
    parser.add_argument("--before", required=True, type=Path, help="Previous best coverage.json")
    parser.add_argument("--after", required=True, type=Path, help="Current run coverage.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        diff = compare_coverage_files(before_path=args.before, after_path=args.after)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    json.dump(diff, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if diff["regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
