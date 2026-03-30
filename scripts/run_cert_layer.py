#!/usr/bin/env python3
"""Run the deterministic certification layer across every example template."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_layers import (
    ROOT,
    RUNS_DIR,
    certification_summary_path_for,
    load_json,
    update_run_summary,
    write_json,
)
from compare_coverage import compare_coverage_files
from export_layout_inventory import build_inventory
from generate_coverage_matrix import build_coverage_matrix
from generate_layout_cert_suite import build_cert_suite
from generate_layout_fixtures import build_fixture_payloads, write_fixture_payloads

from agent_slides.io import read_deck, resolve_manifest_path
from agent_slides.io.template_reader import read_template_manifest
from agent_slides.model.layout_provider import resolve_layout_provider
from agent_slides.render_oracle import generate_render_signals


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Run ID under runs/<id>/")
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=ROOT / "examples",
        help="Directory containing example PPTX templates",
    )
    return parser.parse_args(argv)


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def discover_example_templates(examples_dir: Path) -> list[Path]:
    return sorted(path for path in examples_dir.glob("*.pptx") if path.is_file())


def invoke_cli(*args: str, cwd: Path | None = None) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
    cmd = ["uv", "run", "--project", str(ROOT), "agent-slides", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or ROOT, check=False)
    return result.returncode, _parse_json(result.stdout), _parse_json(result.stderr)


def _coverage_metric(summary: dict[str, Any]) -> float | None:
    layers = summary.get("layers")
    if isinstance(layers, dict):
        certification = layers.get("certification")
        if isinstance(certification, dict):
            value = certification.get("overall_coverage_pct")
            if isinstance(value, int | float):
                return float(value)
    return None


def _certification_decision(summary: dict[str, Any]) -> str | None:
    layers = summary.get("layers")
    if isinstance(layers, dict):
        certification = layers.get("certification")
        if isinstance(certification, dict):
            decision = certification.get("decision")
            if isinstance(decision, str):
                return decision
    return None


def previous_best_certification_summary(*, current_run_id: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for summary_path in sorted(RUNS_DIR.glob("*/summary.json")):
        if summary_path.parent.name == current_run_id:
            continue
        summary = load_json(summary_path)
        if summary is None:
            continue
        if _certification_decision(summary) == "reject":
            continue
        metric = _coverage_metric(summary)
        if metric is None:
            continue
        candidates.append(summary)
    if not candidates:
        return None
    return max(candidates, key=lambda item: _coverage_metric(item) or 0.0)


def _write_inventory(manifest: dict[str, Any], output_path: Path) -> dict[str, Any]:
    inventory = build_inventory(manifest)
    write_json(output_path, inventory)
    return inventory


def _write_render_signals(deck_path: Path) -> Path:
    deck = read_deck(str(deck_path))
    provider = resolve_layout_provider(resolve_manifest_path(str(deck_path), deck))
    signals = generate_render_signals(deck, provider)
    output_path = deck_path.parent / "signals.json"
    output_path.write_text(json.dumps(signals, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_deck_artifacts(deck_path: Path) -> dict[str, Any]:
    pptx_path = deck_path.with_suffix(".pptx")
    exit_code, stdout_payload, stderr_payload = invoke_cli("build", str(deck_path), "-o", str(pptx_path), cwd=deck_path.parent)
    success = exit_code == 0 and pptx_path.exists()
    artifact = {
        "deck_path": str(deck_path),
        "pptx_path": str(pptx_path),
        "build_success": success,
    }
    if stdout_payload is not None:
        artifact["build_result"] = stdout_payload
    if stderr_payload is not None:
        artifact["build_error"] = stderr_payload

    write_json(deck_path.parent / "scores.json", {"build_success": 1.0 if success else 0.0})
    _write_render_signals(deck_path)
    return artifact


def run_template_pipeline(*, template_path: Path, run_dir: Path) -> dict[str, Any]:
    template_slug = template_path.stem
    template_dir = run_dir / "certification" / template_slug
    template_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = template_dir / "manifest.json"
    inventory_path = template_dir / "inventory.json"
    fixtures_dir = template_dir / "fixtures"
    suite_root = template_dir / "suite"

    learn_result = read_template_manifest(template_path, manifest_path)
    inventory = _write_inventory(learn_result.manifest, inventory_path)
    fixture_payloads = build_fixture_payloads(inventory)
    written_fixtures = write_fixture_payloads(fixture_payloads, fixtures_dir)
    deck_paths = build_cert_suite(manifest_path, inventory, fixture_payloads, output_dir=suite_root)
    suite_dir = suite_root / template_slug

    build_artifacts = [build_deck_artifacts(deck_path) for deck_path in deck_paths]
    coverage_path = template_dir / "coverage.json"
    coverage = build_coverage_matrix(suite_dir=suite_dir, output_path=coverage_path)
    write_json(coverage_path, coverage)
    template_summary = {
        "template": template_slug,
        "source_template": str(template_path),
        "manifest_path": str(manifest_path.relative_to(run_dir)),
        "inventory_path": str(inventory_path.relative_to(run_dir)),
        "fixtures_dir": str(fixtures_dir.relative_to(run_dir)),
        "suite_dir": str(suite_dir.relative_to(run_dir)),
        "coverage_path": str(coverage_path.relative_to(run_dir)),
        "layouts_testable": coverage["testable"],
        "coverage_pct": coverage["coverage_pct"],
        "deck_count": len(deck_paths),
        "fixture_files": [path.name for path in written_fixtures],
        "build_failures": sum(1 for artifact in build_artifacts if not artifact["build_success"]),
    }
    write_json(template_dir / "template-summary.json", template_summary)
    return template_summary


def load_coverage_diff(
    *,
    current_run_dir: Path,
    baseline_summary: dict[str, Any] | None,
    current_templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if baseline_summary is None:
        return []

    layers = baseline_summary.get("layers")
    if not isinstance(layers, dict):
        return []
    certification = layers.get("certification")
    if not isinstance(certification, dict):
        return []
    baseline_templates = certification.get("templates")
    if not isinstance(baseline_templates, list):
        return []

    baseline_by_name = {
        entry.get("template"): entry
        for entry in baseline_templates
        if isinstance(entry, dict) and isinstance(entry.get("template"), str)
    }

    diffs: list[dict[str, Any]] = []
    for template in current_templates:
        template_name = template.get("template")
        coverage_path = template.get("coverage_path")
        if not isinstance(template_name, str) or not isinstance(coverage_path, str):
            continue
        baseline_entry = baseline_by_name.get(template_name)
        if not isinstance(baseline_entry, dict):
            continue
        baseline_coverage_path = baseline_entry.get("coverage_path")
        if not isinstance(baseline_coverage_path, str):
            continue

        before_path = RUNS_DIR / str(baseline_summary.get("run_id", "")) / baseline_coverage_path
        after_path = current_run_dir / coverage_path
        if not before_path.exists() or not after_path.exists():
            continue

        diff = compare_coverage_files(before_path=before_path, after_path=after_path)
        regressions = diff.get("regressions", [])
        if regressions:
            diffs.append(
                {
                    "template": template_name,
                    "coverage_diff": diff,
                }
            )
    return diffs


def evaluate_reject_reasons(
    *,
    baseline_summary: dict[str, Any] | None,
    overall_coverage_pct: float,
    coverage_diffs: list[dict[str, Any]],
) -> list[str]:
    if baseline_summary is None:
        return []

    reject_reasons: list[str] = []
    baseline_coverage = _coverage_metric(baseline_summary)
    if baseline_coverage is not None and overall_coverage_pct < baseline_coverage:
        reject_reasons.append(
            f"coverage regressed from {baseline_coverage:.1f} to {overall_coverage_pct:.1f}"
        )

    for template_diff in coverage_diffs:
        template_name = template_diff.get("template")
        diff = template_diff.get("coverage_diff")
        if not isinstance(template_name, str) or not isinstance(diff, dict):
            continue
        regressions = diff.get("regressions", [])
        if not isinstance(regressions, list) or not regressions:
            continue
        slugs = ", ".join(
            sorted(
                str(regression["slug"])
                for regression in regressions
                if isinstance(regression, dict) and isinstance(regression.get("slug"), str)
            )
        )
        if slugs:
            reject_reasons.append(f"{template_name}: layout regressions: {slugs}")
    return reject_reasons


def build_layer_summary(*, run_id: str, templates: list[dict[str, Any]]) -> dict[str, Any]:
    total_passed = sum(int(template.get("passed", 0)) for template in templates)
    total_testable = sum(int(template.get("testable", 0)) for template in templates)
    overall_coverage_pct = round(
        (total_passed / total_testable * 100) if total_testable > 0 else 0.0,
        1,
    )
    baseline_summary = previous_best_certification_summary(current_run_id=run_id)
    current_run_dir = RUNS_DIR / run_id
    coverage_diffs = load_coverage_diff(
        current_run_dir=current_run_dir,
        baseline_summary=baseline_summary,
        current_templates=templates,
    )
    reject_reasons = evaluate_reject_reasons(
        baseline_summary=baseline_summary,
        overall_coverage_pct=overall_coverage_pct,
        coverage_diffs=coverage_diffs,
    )
    layer: dict[str, Any] = {
        "templates": templates,
        "overall_coverage_pct": overall_coverage_pct,
        "decision": "reject" if reject_reasons else "accept",
        "reject_reasons": reject_reasons,
    }
    if baseline_summary is not None:
        layer["previous_best_run_id"] = baseline_summary.get("run_id")
        layer["previous_best_overall_coverage_pct"] = _coverage_metric(baseline_summary)
    if coverage_diffs:
        layer["coverage_diffs"] = coverage_diffs
    return layer


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    templates = discover_example_templates(args.examples_dir)
    if not templates:
        print(f"No example PPTX templates found in {args.examples_dir}", file=sys.stderr)
        return 1

    run_dir = RUNS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    template_summaries = [run_template_pipeline(template_path=template_path, run_dir=run_dir) for template_path in templates]
    certification_layer = build_layer_summary(run_id=args.run_id, templates=template_summaries)

    certification_summary = {
        "run_id": args.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layer": "certification",
        **certification_layer,
    }
    write_json(certification_summary_path_for(args.run_id), certification_summary)
    update_run_summary(
        args.run_id,
        layer_name="certification",
        layer_payload=certification_layer,
    )

    print(json.dumps({"certification": certification_summary, "summary_path": str((run_dir / "summary.json"))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
