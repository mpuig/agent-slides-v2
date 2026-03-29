#!/usr/bin/env python3
"""Demo research runner: executes the full benchmark pipeline and outputs scores.

Usage:
    python scripts/demo_research.py [--benchmarks strategy-deck,quarterly-update] [--run-id RUN_ID]

Each benchmark produces:
    runs/<run_id>/<benchmark_name>/
        deck.json, deck.computed.json, deck.pptx
        review/  (slide PNGs + report)
        scores.json
    runs/<run_id>/summary.json  (aggregate scores across all benchmarks)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RUNS_DIR = ROOT / "runs"

# Score weights — review_quality is the rendered visual quality from LibreOffice
# screenshots, not a structural proxy. It uses passed/total from the 38-item
# checklist (typography, hierarchy, layout, content, deck-level, AI slop).
WEIGHTS = {
    "review_quality": 25,       # rendered slide quality (passed/total from review)
    "validate_clean": 10,       # no validation warnings
    "no_overflow": 10,          # no text overflow in computed nodes
    "no_unbound": 10,           # no unbound slot warnings
    "placeholder_fill": 10,     # % of expected slots actually filled
    "layout_coverage": 15,      # required layouts present (not just count)
    "slide_count_match": 10,    # actual vs expected slide count
    "build_success": 10,        # PPTX builds without error
}

# Letter grade to numeric (0-1 scale)
GRADE_MAP = {
    "A+": 1.0, "A": 0.95, "A-": 0.90,
    "B+": 0.85, "B": 0.80, "B-": 0.75,
    "C+": 0.70, "C": 0.65, "C-": 0.60,
    "D+": 0.55, "D": 0.50, "D-": 0.45,
    "F": 0.30,
}


def run_cli(*args: str, cwd: Path | None = None) -> dict | None:
    """Run an agent-slides CLI command and return parsed JSON or None on failure."""
    cmd = ["uv", "run", "--project", str(ROOT), "agent-slides", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or ROOT)
    if result.returncode != 0:
        print(f"  FAIL: {' '.join(args)}", file=sys.stderr)
        print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def parse_brief(brief_path: Path) -> dict:
    """Extract structured fields from a benchmark brief markdown file."""
    text = brief_path.read_text()
    fields: dict = {"name": brief_path.stem, "path": str(brief_path)}

    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("## Template"):
            continue
        if line_stripped.startswith("examples/") or line_stripped.startswith("../examples/"):
            fields["template"] = line_stripped
        if line_stripped.startswith("## Expected slide count"):
            continue

    # Parse expected slide count range
    in_slide_count = False
    in_layout_variety = False
    for line in text.splitlines():
        line_stripped = line.strip()
        if "Expected slide count" in line_stripped:
            in_slide_count = True
            continue
        if in_slide_count and line_stripped:
            parts = line_stripped.split("-")
            try:
                fields["min_slides"] = int(parts[0])
                fields["max_slides"] = int(parts[-1])
            except ValueError:
                pass
            in_slide_count = False
        if "Layout variety" in line_stripped:
            in_layout_variety = True
            continue
        if in_layout_variety and line_stripped:
            for word in line_stripped.split():
                try:
                    fields["min_layouts"] = int(word)
                    break
                except ValueError:
                    continue
            in_layout_variety = False

    # Parse required layouts from numbered list items like "1. **title_slide** — ..."
    required_layouts = []
    for line in text.splitlines():
        match = re.match(r'\s*\d+\.\s+\*\*(\w+)\*\*', line)
        if match:
            required_layouts.append(match.group(1))
    if required_layouts:
        fields["required_layouts"] = required_layouts

    # Parse image-required layouts (lines mentioning "Fill image slot" or "MUST have real images")
    image_layouts = []
    for line in text.splitlines():
        match = re.match(r'\s*\d+\.\s+\*\*(\w+)\*\*', line)
        if match and ("image" in line.lower() and ("fill" in line.lower() or "must" in line.lower())):
            image_layouts.append(match.group(1))
    if image_layouts:
        fields["image_required_layouts"] = image_layouts

    return fields


def score_deck(deck_path: Path, brief: dict, run_dir: Path) -> dict:
    """Score a built deck against deterministic and visual metrics."""
    scores: dict = {}

    deck_cwd = deck_path.parent

    # 1. Build success
    pptx_path = run_dir / "deck.pptx"
    build_result = run_cli("build", str(deck_path), "-o", str(pptx_path), cwd=deck_cwd)
    scores["build_success"] = 1.0 if (build_result and pptx_path.exists()) else 0.0

    # 2. Validate
    validate_result = run_cli("validate", str(deck_path), cwd=deck_cwd)
    if validate_result and validate_result.get("ok"):
        warnings = validate_result["data"].get("warnings", [])
        scores["validate_clean"] = 1.0 if not warnings else max(0, 1.0 - len(warnings) * 0.2)
        scores["validate_warnings"] = len(warnings)
        scores["validate_details"] = [
            {"code": w["code"], "severity": w["severity"], "message": w["message"]}
            for w in warnings[:10]
        ]
    else:
        scores["validate_clean"] = 0.0
        scores["validate_warnings"] = -1

    # 3. Read deck info for computed analysis
    info_result = run_cli("info", str(deck_path), cwd=deck_cwd)
    if info_result:
        slides = info_result.get("slides", [])
        scores["slide_count"] = len(slides)

        # Slide count match
        min_s = brief.get("min_slides", 1)
        max_s = brief.get("max_slides", 100)
        if min_s <= len(slides) <= max_s:
            scores["slide_count_match"] = 1.0
        else:
            distance = min(abs(len(slides) - min_s), abs(len(slides) - max_s))
            scores["slide_count_match"] = max(0, 1.0 - distance * 0.2)

        # Layout coverage — check required layouts are present, not just count
        layouts_used = set()
        for slide in slides:
            layouts_used.add(slide.get("layout", "unknown"))
        scores["layouts_used"] = sorted(layouts_used)

        required_layouts = brief.get("required_layouts", [])
        if required_layouts:
            present = sum(1 for l in required_layouts if l in layouts_used)
            scores["layout_coverage"] = present / len(required_layouts)
            scores["required_layouts_missing"] = sorted(
                l for l in required_layouts if l not in layouts_used
            )
        else:
            # Fallback to generic variety check
            min_layouts = brief.get("min_layouts", 2)
            scores["layout_coverage"] = min(1.0, len(layouts_used) / min_layouts)

        # Image slot validation — check image-required layouts have actual images
        image_required = brief.get("image_required_layouts", [])
        if image_required:
            image_filled = 0
            image_expected = 0
            for slide in slides:
                if slide.get("layout") in image_required:
                    image_expected += 1
                    for node in slide.get("nodes", []):
                        if node.get("type") == "image" and node.get("image_path"):
                            image_filled += 1
                            break
            scores["image_fill"] = (image_filled / image_expected) if image_expected > 0 else 1.0
            scores["image_expected"] = image_expected
            scores["image_filled"] = image_filled
        else:
            scores["image_fill"] = 1.0

        # Overflow and unbound analysis
        overflow_count = 0
        unbound_count = 0
        total_text_nodes = 0
        filled_slots = 0
        total_slots = 0
        for slide in slides:
            computed = slide.get("computed", {})
            nodes = slide.get("nodes", [])
            for node in nodes:
                node_id = node.get("node_id", "")
                comp = computed.get(node_id, {})
                if node.get("type") == "text":
                    total_text_nodes += 1
                    if comp.get("text_overflow"):
                        overflow_count += 1
                if node.get("slot_binding"):
                    is_unfillable_image = (
                        node.get("type") == "image" and not node.get("image_path")
                    )
                    if is_unfillable_image:
                        continue
                    total_slots += 1
                    content = node.get("content", {})
                    blocks = content.get("blocks", [])
                    has_text = any(b.get("text", "").strip() for b in blocks)
                    has_image = node.get("type") == "image" and node.get("image_path")
                    if has_text or has_image:
                        filled_slots += 1
                if not node.get("slot_binding") and node.get("type") == "text":
                    unbound_count += 1

        scores["overflow_count"] = overflow_count
        scores["no_overflow"] = 1.0 if overflow_count == 0 else max(0, 1.0 - overflow_count * 0.25)
        scores["unbound_count"] = unbound_count
        scores["no_unbound"] = 1.0 if unbound_count == 0 else max(0, 1.0 - unbound_count * 0.25)
        scores["placeholder_fill"] = (filled_slots / total_slots) if total_slots > 0 else 0.0
        scores["filled_slots"] = filled_slots
        scores["total_slots"] = total_slots
    else:
        for key in ["slide_count_match", "layout_coverage", "no_overflow", "no_unbound", "placeholder_fill"]:
            scores[key] = 0.0

    # 4. Review — rendered visual quality from LibreOffice screenshots
    review_dir = run_dir / "review"
    review_result = run_cli("review", str(deck_path), "-o", str(review_dir), cwd=deck_cwd)
    if review_result and review_result.get("ok"):
        grade = review_result["data"].get("overall_grade", "F")
        scores["review_grade"] = grade
        scores["review_slides"] = review_result["data"].get("slides", 0)
        # Convert to numeric: use passed/total ratio from report.json if available,
        # fall back to letter grade conversion
        report_json = review_dir / "report.json"
        if report_json.exists():
            try:
                report = json.loads(report_json.read_text())
                overall = report.get("active", {}).get("overall", {})
                passed = overall.get("passed", 0)
                total = overall.get("total", 1)
                scores["review_quality"] = passed / total if total > 0 else 0.0
                scores["review_passed"] = passed
                scores["review_total"] = total
            except (json.JSONDecodeError, KeyError):
                scores["review_quality"] = GRADE_MAP.get(grade, 0.3)
        else:
            scores["review_quality"] = GRADE_MAP.get(grade, 0.3)
    else:
        scores["review_grade"] = "N/A"
        scores["review_quality"] = 0.0

    # 5. Composite score
    composite = 0.0
    total_weight = 0
    for metric, weight in WEIGHTS.items():
        value = scores.get(metric, 0.0)
        if isinstance(value, (int, float)):
            composite += value * weight
            total_weight += weight
    scores["composite"] = round(composite / total_weight * 100, 1) if total_weight > 0 else 0.0

    return scores


def ensure_symlinks(bench_dir: Path) -> None:
    """Create symlinks so relative paths in deck.json resolve correctly."""
    examples_link = bench_dir / "examples"
    if not examples_link.exists():
        examples_link.symlink_to(ROOT / "examples")

    artifacts_link = bench_dir / ".artifacts"
    if not artifacts_link.exists():
        artifacts_link.symlink_to(ROOT / ".artifacts")


def run_benchmark(brief_path: Path, run_dir: Path, manifest_path: Path | None = None) -> dict:
    """Run a single benchmark: init deck, build, score."""
    brief = parse_brief(brief_path)
    bench_dir = run_dir / brief["name"]
    bench_dir.mkdir(parents=True, exist_ok=True)
    ensure_symlinks(bench_dir)

    deck_path = bench_dir / "deck.json"

    if deck_path.exists():
        print(f"  Scoring existing deck: {deck_path}")
        scores = score_deck(deck_path, brief, bench_dir)
    else:
        print(f"  No deck.json found at {deck_path}, skipping.")
        scores = {"composite": 0.0, "error": "no deck.json"}

    scores_path = bench_dir / "scores.json"
    scores_path.write_text(json.dumps(scores, indent=2))
    print(f"  Composite score: {scores['composite']}")

    return {"benchmark": brief["name"], "scores": scores}


def main():
    parser = argparse.ArgumentParser(description="Demo research runner")
    parser.add_argument(
        "--benchmarks",
        default="minimal-title-body,quarterly-update,strategy-deck,layout-showcase",
        help="Comma-separated benchmark names",
    )
    parser.add_argument("--run-id", default=None, help="Run ID (default: timestamp)")
    parser.add_argument("--manifest", default=None, help="Path to template manifest")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest) if args.manifest else None

    benchmark_names = [b.strip() for b in args.benchmarks.split(",")]
    results = []

    for name in benchmark_names:
        brief_path = BENCHMARKS_DIR / f"{name}.md"
        if not brief_path.exists():
            print(f"Benchmark not found: {brief_path}", file=sys.stderr)
            continue
        print(f"\n=== Benchmark: {name} ===")
        result = run_benchmark(brief_path, run_dir, manifest_path)
        results.append(result)

    composites = [r["scores"]["composite"] for r in results if "composite" in r["scores"]]
    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmarks": results,
        "mean_composite": round(sum(composites) / len(composites), 1) if composites else 0.0,
    }

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== Summary: mean_composite={summary['mean_composite']} ===")
    print(f"Results: {summary_path}")


if __name__ == "__main__":
    main()
