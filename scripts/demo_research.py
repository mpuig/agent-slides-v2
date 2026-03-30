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
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_coverage import compare_coverage_files

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RUNS_DIR = ROOT / "runs"
REVIEW_REGRESSION_THRESHOLD = 0.05

# Deterministic score weights
WEIGHTS = {
    "validate_clean": 20,  # no validation warnings
    "no_overflow": 15,  # no text overflow in computed nodes
    "no_unbound": 15,  # no unbound slot warnings
    "placeholder_fill": 20,  # % of expected slots actually filled
    "layout_coverage": 10,  # required layouts present / expected set, or generic variety fallback
    "slide_count_match": 10,  # actual vs expected slide count
    "build_success": 10,  # PPTX builds without error
    "review_quality": 20,  # visual review passed/total ratio when available
}

# Match bold slugs only in numbered list items like "1. **title_slide** — ..."
BOLD_SLUG_PATTERN = re.compile(r"^\s*\d+\.\s+\*\*([a-z0-9_]+)\*\*")
SOURCE_LINE_PATTERN = re.compile(
    r"at least\s+(\d+)\s+slides?\s+should\s+include\s+a\s+source line", re.IGNORECASE
)
WORD_PATTERN = re.compile(r"\b[\w'-]+\b")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _node_text(node: dict) -> str:
    content = node.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, dict):
        return ""
    blocks = content.get("blocks", [])
    if not isinstance(blocks, list):
        return ""
    texts = [
        block.get("text", "").strip() for block in blocks if isinstance(block, dict)
    ]
    return "\n".join(text for text in texts if text)


def _word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def _has_source_line(slide: dict) -> bool:
    return any(
        _node_text(node).casefold().startswith(("source:", "sources:"))
        for node in slide.get("nodes", [])
    )


def _is_valid_image_path(image_path: str | None, deck_cwd: Path) -> bool:
    if not image_path:
        return False
    path = Path(image_path)
    if not path.is_absolute():
        path = deck_cwd / path
    return path.exists()


def _brief_compliance_for_slides(
    slides: list[dict], brief: dict, deck_cwd: Path
) -> dict:
    layouts_used = {slide.get("layout", "unknown") for slide in slides}

    required_layouts = brief.get("required_layouts", [])
    required_layouts_present = [
        slug for slug in required_layouts if slug in layouts_used
    ]
    required_layouts_missing = [
        slug for slug in required_layouts if slug not in layouts_used
    ]

    slides_by_layout: dict[str, list[dict]] = {}
    for slide in slides:
        slides_by_layout.setdefault(slide.get("layout", "unknown"), []).append(slide)

    image_required_layouts = brief.get("image_required_layouts", [])
    image_layouts_expected = len(image_required_layouts)
    image_layouts_filled = 0
    image_files_valid = True

    narrow_layouts = set(brief.get("narrow_layouts", []))
    narrow_headings_ok = True
    source_lines_found = 0

    for slide in slides:
        layout = slide.get("layout", "unknown")
        nodes = slide.get("nodes", [])

        if _has_source_line(slide):
            source_lines_found += 1

        if layout in narrow_layouts:
            heading_nodes = [
                node
                for node in nodes
                if node.get("type") == "text"
                and node.get("slot_binding") == "heading"
                and _node_text(node)
            ]
            if any(_word_count(_node_text(node)) > 5 for node in heading_nodes):
                narrow_headings_ok = False

    for layout in image_required_layouts:
        slide_group = slides_by_layout.get(layout, [])
        valid_image_found = any(
            node.get("type") == "image"
            and _is_valid_image_path(node.get("image_path"), deck_cwd)
            for slide in slide_group
            for node in slide.get("nodes", [])
        )
        if valid_image_found:
            image_layouts_filled += 1
        else:
            image_files_valid = False

    return {
        "required_layouts_present": required_layouts_present,
        "required_layouts_missing": required_layouts_missing,
        "image_layouts_filled": image_layouts_filled,
        "image_layouts_expected": image_layouts_expected,
        "image_files_valid": image_files_valid,
        "narrow_headings_ok": narrow_headings_ok,
        "source_lines_found": source_lines_found,
    }


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def invoke_cli(
    *args: str, cwd: Path | None = None
) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
    """Run an agent-slides CLI command and return the exit code plus parsed stdout/stderr JSON."""
    cmd = ["uv", "run", "--project", str(ROOT), "agent-slides", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or ROOT)
    stdout_payload = _parse_json(result.stdout)
    stderr_payload = _parse_json(result.stderr)
    if result.returncode != 0:
        print(f"  FAIL: {' '.join(args)}", file=sys.stderr)
        print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
    return result.returncode, stdout_payload, stderr_payload


def run_cli(*args: str, cwd: Path | None = None) -> dict[str, Any] | None:
    """Run an agent-slides CLI command and return parsed stdout JSON or None on failure."""
    returncode, stdout_payload, _ = invoke_cli(*args, cwd=cwd)
    if returncode != 0:
        return None
    return stdout_payload


def base_scores(*, error: str | None = None) -> dict[str, Any]:
    scores: dict[str, Any] = {
        "build_success": 0.0,
        "validate_clean": 0.0,
        "validate_warnings": -1,
        "slide_count_match": 0.0,
        "slide_count": 0,
        "layout_variety": 0.0,
        "layouts_used": [],
        "overflow_count": 0,
        "no_overflow": 0.0,
        "unbound_count": 0,
        "no_unbound": 0.0,
        "placeholder_fill": 0.0,
        "filled_slots": 0,
        "total_slots": 0,
        "review_grade": "N/A",
        "review_slides": 0,
        "review_quality": 0.0,
        "review_passed": 0,
        "review_total": 0,
        "review_available": False,
    }
    if error is not None:
        scores["error"] = error
    return scores


def compute_composite(scores: dict[str, Any]) -> float:
    composite = 0.0
    total_weight = 0
    for metric, weight in WEIGHTS.items():
        if metric == "review_quality" and not scores.get("review_available", False):
            continue
        value = scores.get(metric, 0.0)
        if isinstance(value, (int, float)):
            composite += value * weight
            total_weight += weight
    return round(composite / total_weight * 100, 1) if total_weight > 0 else 0.0


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _parse_json(path.read_text(encoding="utf-8"))


def load_review_metrics(report_json_path: Path) -> dict[str, Any]:
    report = load_json(report_json_path) or {}
    active = report.get("active", {})
    overall = active.get("overall", {})
    passed = int(overall.get("passed", 0) or 0)
    total = int(overall.get("total", 0) or 0)
    return {
        "review_available": True,
        "review_passed": passed,
        "review_total": total,
        "review_quality": round(passed / total, 4) if total > 0 else 0.0,
        "review_grade": overall.get("grade", active.get("grade", "N/A")),
    }


def previous_best_summary(*, current_run_id: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for summary_path in sorted(RUNS_DIR.glob("*/summary.json")):
        if summary_path.parent.name == current_run_id:
            continue
        summary = load_json(summary_path)
        if summary is None:
            continue
        if summary.get("decision") == "reject":
            continue
        if isinstance(summary.get("mean_composite"), (int, float)):
            candidates.append(summary)
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item.get("mean_composite", 0.0)))


def coverage_path_for_run(run_id: str) -> Path:
    return RUNS_DIR / run_id / "coverage.json"


def load_coverage_diff(
    *, current_run_id: str, baseline_summary: dict[str, Any] | None
) -> dict[str, Any] | None:
    if baseline_summary is None:
        return None

    baseline_run_id = baseline_summary.get("run_id")
    if not isinstance(baseline_run_id, str) or not baseline_run_id:
        return None

    before_path = coverage_path_for_run(baseline_run_id)
    after_path = coverage_path_for_run(current_run_id)
    if not before_path.exists() or not after_path.exists():
        return None

    return compare_coverage_files(before_path=before_path, after_path=after_path)


def evaluate_reject_reasons(
    results: list[dict[str, Any]],
    *,
    current_mean_composite: float,
    baseline_summary: dict[str, Any] | None,
    coverage_diff: dict[str, Any] | None = None,
) -> list[str]:
    if baseline_summary is None:
        return []

    reject_reasons: list[str] = []
    baseline_mean = float(baseline_summary.get("mean_composite", 0.0))
    if current_mean_composite < baseline_mean:
        reject_reasons.append(
            f"composite regressed from {baseline_mean:.1f} to {current_mean_composite:.1f}"
        )

    baseline_scores = {
        benchmark.get("benchmark"): benchmark.get("scores", {})
        for benchmark in baseline_summary.get("benchmarks", [])
        if isinstance(benchmark, dict)
    }

    for result in results:
        benchmark_name = result.get("benchmark")
        if not isinstance(benchmark_name, str):
            continue
        current_scores = result.get("scores", {})
        if not isinstance(current_scores, dict):
            continue
        baseline_benchmark_scores = baseline_scores.get(benchmark_name)
        if not isinstance(baseline_benchmark_scores, dict):
            continue
        baseline_had_review = baseline_benchmark_scores.get("review_available", False)
        current_has_review = current_scores.get("review_available", False)

        if baseline_had_review and not current_has_review:
            reject_reasons.append(
                f"{benchmark_name}: review data lost — baseline had review but current does not"
            )
            continue

        if not baseline_had_review or not current_has_review:
            continue

        current_quality = float(current_scores.get("review_quality", 0.0))
        baseline_quality = float(baseline_benchmark_scores.get("review_quality", 0.0))
        if baseline_quality - current_quality > REVIEW_REGRESSION_THRESHOLD:
            reject_reasons.append(
                f"{benchmark_name}: review_quality regressed from {baseline_quality:.3f} to {current_quality:.3f}"
            )

    regressions = (
        coverage_diff.get("regressions", []) if isinstance(coverage_diff, dict) else []
    )
    if regressions:
        regressed_slugs = ", ".join(
            sorted(
                str(regression["slug"])
                for regression in regressions
                if isinstance(regression, dict)
                and isinstance(regression.get("slug"), str)
            )
        )
        if regressed_slugs:
            reject_reasons.append(f"layout regressions: {regressed_slugs}")

    return reject_reasons


def build_summary(*, run_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    composites = [
        r["scores"]["composite"] for r in results if "composite" in r["scores"]
    ]
    mean_composite = round(sum(composites) / len(composites), 1) if composites else 0.0
    baseline_summary = previous_best_summary(current_run_id=run_id)
    coverage_diff = load_coverage_diff(
        current_run_id=run_id, baseline_summary=baseline_summary
    )
    reject_reasons = evaluate_reject_reasons(
        results,
        current_mean_composite=mean_composite,
        baseline_summary=baseline_summary,
        coverage_diff=coverage_diff,
    )
    review_unavailable = [
        result["benchmark"]
        for result in results
        if not result.get("scores", {}).get("review_available", False)
    ]
    summary: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmarks": results,
        "mean_composite": mean_composite,
        "decision": "reject" if reject_reasons else "accept",
        "reject_reasons": reject_reasons,
        "review_unavailable_benchmarks": review_unavailable,
    }
    if baseline_summary is not None:
        summary["previous_best_run_id"] = baseline_summary.get("run_id")
        summary["previous_best_mean_composite"] = baseline_summary.get("mean_composite")
    if coverage_diff is not None:
        summary["coverage_diff"] = coverage_diff
    return summary


def parse_brief(brief_path: Path) -> dict:
    """Extract structured fields from a benchmark brief markdown file."""
    text = brief_path.read_text(encoding="utf-8")
    fields: dict = {
        "name": brief_path.stem,
        "path": str(brief_path),
        "required_layouts": [],
        "image_required_layouts": [],
        "narrow_layouts": [],
        "min_source_lines": 0,
    }

    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("## Template"):
            continue
        if line_stripped.startswith("examples/") or line_stripped.startswith(
            "../examples/"
        ):
            fields["template"] = line_stripped
        if line_stripped.startswith("## Expected slide count"):
            continue

    # Parse expected slide count range
    in_slide_count = False
    in_layout_variety = False
    for line in text.splitlines():
        line_stripped = line.strip()
        slug_match = BOLD_SLUG_PATTERN.match(line_stripped)
        slugs = [slug_match.group(1)] if slug_match else []
        if slugs:
            fields["required_layouts"].extend(slugs)
            line_lower = line_stripped.casefold()
            if "image" in line_lower and any(
                keyword in line_lower for keyword in ("fill", "filled", "real image")
            ):
                fields["image_required_layouts"].extend(slugs)
            if any(
                keyword in line_lower
                for keyword in (
                    "narrow",
                    "short heading",
                    "headings short",
                    "keep headings short",
                    "short because",
                )
            ):
                fields["narrow_layouts"].extend(slugs)

        source_line_match = SOURCE_LINE_PATTERN.search(line_stripped)
        if source_line_match:
            fields["min_source_lines"] = int(source_line_match.group(1))

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

    fields["required_layouts"] = _dedupe(fields["required_layouts"])
    fields["image_required_layouts"] = _dedupe(fields["image_required_layouts"])
    fields["narrow_layouts"] = _dedupe(fields["narrow_layouts"])

    return fields


def score_deck(deck_path: Path, brief: dict, run_dir: Path) -> dict:
    """Score a built deck against deterministic metrics."""
    scores = base_scores()

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
        scores["validate_clean"] = (
            1.0 if not warnings else max(0, 1.0 - len(warnings) * 0.2)
        )
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
        brief_compliance = _brief_compliance_for_slides(slides, brief, deck_cwd)
        scores["brief_compliance"] = brief_compliance

        required_layouts = brief.get("required_layouts", [])
        if required_layouts:
            scores["layout_coverage"] = len(
                brief_compliance["required_layouts_present"]
            ) / len(required_layouts)
        else:
            min_layouts = brief.get("min_layouts", 2)
            scores["layout_coverage"] = min(1.0, len(layouts_used) / min_layouts)
        scores["layout_variety"] = scores["layout_coverage"]

        # Overflow and unbound analysis
        overflow_count = 0
        unbound_count = 0
        filled_slots = 0
        total_slots = 0
        for slide in slides:
            computed = slide.get("computed", {})
            nodes = slide.get("nodes", [])
            for node in nodes:
                node_id = node.get("node_id", "")
                comp = computed.get(node_id, {})
                if node.get("type") == "text":
                    if comp.get("text_overflow"):
                        overflow_count += 1
                if node.get("slot_binding"):
                    # Exclude image slots without image_path from scoring:
                    # these can't be filled without real image assets and
                    # should not penalize text-only deck builds.
                    is_unfillable_image = node.get("type") == "image" and not node.get(
                        "image_path"
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
        scores["no_overflow"] = (
            1.0 if overflow_count == 0 else max(0, 1.0 - overflow_count * 0.25)
        )
        scores["unbound_count"] = unbound_count
        scores["no_unbound"] = (
            1.0 if unbound_count == 0 else max(0, 1.0 - unbound_count * 0.25)
        )
        generic_fill = (filled_slots / total_slots) if total_slots > 0 else 0.0
        image_layouts_expected = brief_compliance["image_layouts_expected"]
        image_fill_ratio = (
            brief_compliance["image_layouts_filled"] / image_layouts_expected
            if image_layouts_expected > 0
            else 1.0
        )
        scores["placeholder_fill"] = min(generic_fill, image_fill_ratio)
        scores["filled_slots"] = filled_slots
        scores["total_slots"] = total_slots
    else:
        scores["brief_compliance"] = {
            "required_layouts_present": [],
            "required_layouts_missing": list(brief.get("required_layouts", [])),
            "image_layouts_filled": 0,
            "image_layouts_expected": 0,
            "image_files_valid": True,
            "narrow_headings_ok": True,
            "source_lines_found": 0,
        }
        for key in [
            "slide_count_match",
            "layout_coverage",
            "no_overflow",
            "no_unbound",
            "placeholder_fill",
        ]:
            scores[key] = 0.0
        scores["layout_variety"] = 0.0

    # 4. Review (render PNGs)
    review_dir = run_dir / "review"
    review_exit_code, review_result, review_error = invoke_cli(
        "review", str(deck_path), "-o", str(review_dir), cwd=deck_cwd
    )
    if review_exit_code == 0 and review_result and review_result.get("ok"):
        review_data = review_result.get("data", {})
        scores["review_slides"] = review_data.get("slides", 0)
        scores["review_grade"] = review_data.get("overall_grade", "N/A")
        report_json_path = review_data.get("report_json_path")
        if isinstance(report_json_path, str):
            scores.update(load_review_metrics(Path(report_json_path)))
    elif review_error:
        scores["review_error"] = review_error.get("error", {}).get(
            "message", "review failed"
        )

    composite_score = compute_composite(scores)
    brief_compliance = scores.get("brief_compliance", {})
    compliance_cap = 1.0
    required_layouts = brief.get("required_layouts", [])
    if required_layouts:
        compliance_cap = min(compliance_cap, scores.get("layout_coverage", 0.0))
    image_layouts_expected = brief_compliance.get("image_layouts_expected", 0)
    if image_layouts_expected:
        compliance_cap = min(
            compliance_cap,
            brief_compliance.get("image_layouts_filled", 0) / image_layouts_expected,
        )
    if brief.get("narrow_layouts") and not brief_compliance.get(
        "narrow_headings_ok", True
    ):
        compliance_cap = min(compliance_cap, 0.8)
    min_source_lines = brief.get("min_source_lines", 0)
    if min_source_lines > 0:
        found = brief_compliance.get("source_lines_found", 0)
        # Floor at 0.5 — missing source lines is a penalty, not a zero-out
        source_ratio = max(0.5, min(1.0, found / min_source_lines))
        compliance_cap = min(compliance_cap, source_ratio)

    scores["composite"] = round(min(composite_score, compliance_cap * 100), 1)

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


def stage_deck_images(deck_path: Path) -> None:
    """Copy images referenced in a deck into the deck's directory tree.

    The build command's path traversal guard requires images to resolve
    inside the deck's parent directory. When agents use relative paths
    that traverse out (e.g., ../../../examples/images/), or when symlinks
    resolve outside the deck dir, the build fails. This function copies
    referenced images into deck_dir/_assets/ and rewrites the paths.
    """
    import hashlib
    import shutil

    deck_dir = deck_path.parent
    text = deck_path.read_text(encoding="utf-8")
    data = _parse_json(text)
    if data is None:
        return

    changed = False
    for slide in data.get("slides", []):
        for node in slide.get("nodes", []):
            image_path = node.get("image_path")
            if not image_path:
                continue
            source = Path(image_path)
            if source.is_absolute():
                resolved = source
            else:
                resolved = (deck_dir / source).resolve(strict=False)
            if not resolved.is_file():
                continue
            # Check if the image is already inside the deck dir
            try:
                resolved.relative_to(deck_dir.resolve(strict=False))
                continue  # Already inside, no action needed
            except ValueError:
                pass
            # Copy into _assets/ with hash-based name
            asset_dir = deck_dir / "_assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            try:
                stable_key = str(resolved.relative_to(ROOT.resolve(strict=False)))
            except ValueError:
                stable_key = str(resolved)
            path_hash = hashlib.sha256(stable_key.encode()).hexdigest()[:12]
            local_copy = asset_dir / f"{path_hash}_{resolved.name}"
            shutil.copy2(resolved, local_copy)
            node["image_path"] = str(local_copy.relative_to(deck_dir))
            changed = True

    if changed:
        import json

        deck_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_benchmark(
    brief_path: Path, run_dir: Path, manifest_path: Path | None = None
) -> dict:
    """Run a single benchmark: init deck, build, score."""
    brief = parse_brief(brief_path)
    bench_dir = run_dir / brief["name"]
    bench_dir.mkdir(parents=True, exist_ok=True)
    ensure_symlinks(bench_dir)

    deck_path = bench_dir / "deck.json"

    # Stage images into the deck directory so the build command's traversal guard accepts them
    if deck_path.exists():
        stage_deck_images(deck_path)

    # If a pre-built deck.json exists (created by the experiment cycle agent), score it directly
    if deck_path.exists():
        print(f"  Scoring existing deck: {deck_path}")
        scores = score_deck(deck_path, brief, bench_dir)
    else:
        print(f"  No deck.json found at {deck_path}, skipping.")
        scores = base_scores(error="no deck.json")
        scores["composite"] = compute_composite(scores)

    # Save scores
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

    # Aggregate summary
    summary = build_summary(run_id=run_id, results=results)

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== Summary: mean_composite={summary['mean_composite']} ===")
    print(f"Results: {summary_path}")


if __name__ == "__main__":
    main()
