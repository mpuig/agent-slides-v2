#!/usr/bin/env python3
"""Demo research runner: executes the full benchmark pipeline and outputs scores.

Usage:
    python scripts/demo_research.py [--benchmarks bcg-strategy,bcg-update] [--run-id RUN_ID]

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RUNS_DIR = ROOT / "runs"

# Deterministic score weights
WEIGHTS = {
    "validate_clean": 20,       # no validation warnings
    "no_overflow": 15,          # no text overflow in computed nodes
    "no_unbound": 15,           # no unbound slot warnings
    "placeholder_fill": 20,     # % of expected slots actually filled
    "layout_variety": 10,       # distinct layouts used / expected minimum
    "slide_count_match": 10,    # actual vs expected slide count
    "build_success": 10,        # PPTX builds without error
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
            # Parse "8-10" or "3"
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
            # Extract number from "At least N distinct..."
            for word in line_stripped.split():
                try:
                    fields["min_layouts"] = int(word)
                    break
                except ValueError:
                    continue
            in_layout_variety = False

    return fields


def score_deck(deck_path: Path, brief: dict, run_dir: Path) -> dict:
    """Score a built deck against deterministic metrics."""
    scores: dict = {}

    # Run commands from the deck's directory so relative manifest/template paths resolve
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

        # Layout variety
        layouts_used = set()
        for slide in slides:
            layouts_used.add(slide.get("layout", "unknown"))
        scores["layouts_used"] = sorted(layouts_used)
        min_layouts = brief.get("min_layouts", 2)
        scores["layout_variety"] = min(1.0, len(layouts_used) / min_layouts)

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
                    # Exclude image slots without image_path from scoring:
                    # these can't be filled without real image assets and
                    # should not penalize text-only deck builds.
                    is_unfillable_image = (
                        node.get("type") == "image" and not node.get("image_path")
                    )
                    if is_unfillable_image:
                        continue
                    total_slots += 1
                    # Check if node has content
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
        for key in ["slide_count_match", "layout_variety", "no_overflow", "no_unbound", "placeholder_fill"]:
            scores[key] = 0.0

    # 4. Review (render PNGs)
    review_dir = run_dir / "review"
    review_result = run_cli("review", str(deck_path), "-o", str(review_dir), cwd=deck_cwd)
    if review_result and review_result.get("ok"):
        scores["review_grade"] = review_result["data"].get("overall_grade", "F")
        scores["review_slides"] = review_result["data"].get("slides", 0)
    else:
        scores["review_grade"] = "N/A"

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
    """Create symlinks so relative paths in deck.json resolve correctly.

    Template decks reference the manifest via a relative path (e.g., "bcg.manifest.json")
    and the manifest references the source PPTX (e.g., "../examples/bcg.pptx").
    When decks live in runs/<id>/<bench>/, we symlink from there back to the project root
    so these paths resolve.
    """
    # Symlink examples/ so manifest source paths resolve
    examples_link = bench_dir / "examples"
    if not examples_link.exists():
        examples_link.symlink_to(ROOT / "examples")

    # Symlink .artifacts/ so manifest paths resolve when referenced
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

    # If a pre-built deck.json exists (created by the experiment cycle agent), score it directly
    if deck_path.exists():
        print(f"  Scoring existing deck: {deck_path}")
        scores = score_deck(deck_path, brief, bench_dir)
    else:
        print(f"  No deck.json found at {deck_path}, skipping.")
        scores = {"composite": 0.0, "error": "no deck.json"}

    # Save scores
    scores_path = bench_dir / "scores.json"
    scores_path.write_text(json.dumps(scores, indent=2))
    print(f"  Composite score: {scores['composite']}")

    return {"benchmark": brief["name"], "scores": scores}


def main():
    parser = argparse.ArgumentParser(description="Demo research runner")
    parser.add_argument(
        "--benchmarks",
        default="bcg-strategy,bcg-update,minimal-title-body",
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

    # Aggregate summary
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
