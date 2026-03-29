from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_coverage_matrix.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("generate_coverage_matrix", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_suite_dir(path: Path) -> None:
    (path / "results" / "title_only").mkdir(parents=True)
    (path / "results" / "photo_story").mkdir(parents=True)
    (path / "layout-inventory.json").write_text(
        json.dumps(
            {
                "layouts": [
                    {
                        "slug": "title_only",
                        "usable": True,
                        "testable": True,
                        "requires_image": False,
                        "slot_structure": "heading_only",
                        "exclude_reason": None,
                    },
                    {
                        "slug": "photo_story",
                        "usable": True,
                        "testable": True,
                        "requires_image": True,
                        "slot_structure": "heading_image",
                        "exclude_reason": None,
                    },
                    {
                        "slug": "agenda_table",
                        "usable": True,
                        "testable": False,
                        "requires_image": False,
                        "slot_structure": "multi_slot",
                        "exclude_reason": "unsupported table structure",
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "results" / "title_only" / "nominal.json").write_text(
        json.dumps(
            {
                "layout_slug": "title_only",
                "variant_name": "nominal",
                "build_success": True,
                "signals": {
                    "text_clipped": False,
                    "placeholder_empty": False,
                    "image_missing": False,
                    "font_too_small": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "results" / "photo_story" / "image_missing.json").write_text(
        json.dumps(
            {
                "layout_slug": "photo_story",
                "variant_name": "image_missing",
                "build_success": True,
                "signals": {
                    "text_clipped": False,
                    "placeholder_empty": False,
                    "image_missing": True,
                    "font_too_small": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_generate_coverage_matrix_reports_excluded_layouts_separately(tmp_path: Path) -> None:
    suite_dir = tmp_path / "cert-suite" / "demo-template"
    output_path = tmp_path / "runs" / "run-001" / "coverage.json"
    _write_suite_dir(suite_dir)

    result = _run_script("--suite-dir", str(suite_dir), "--output", str(output_path))

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert output_path.exists()
    assert payload["template"] == "demo-template"
    assert payload["total_layouts"] == 3
    assert payload["usable"] == 3
    assert payload["testable"] == 2
    assert payload["excluded"] == [{"slug": "agenda_table", "reason": "unsupported table structure"}]
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert payload["coverage_pct"] == 50.0
    assert payload["run_id"] == "run-001"

    layouts = {layout["slug"]: layout for layout in payload["layouts"]}
    assert layouts["title_only"]["status"] == "pass"
    assert layouts["title_only"]["variants_passed"] == 1
    assert layouts["photo_story"]["status"] == "fail"
    assert layouts["photo_story"]["failure_reasons"] == ["image missing"]
    assert layouts["agenda_table"]["status"] == "excluded"
    assert layouts["agenda_table"]["failure_reasons"] == []


def test_generate_coverage_matrix_exits_zero_when_all_testable_layouts_pass(tmp_path: Path) -> None:
    suite_dir = tmp_path / "cert-suite" / "brand-template"
    output_path = tmp_path / "runs" / "run-002" / "coverage.json"
    _write_suite_dir(suite_dir)
    (suite_dir / "results" / "photo_story" / "image_present.json").write_text(
        json.dumps(
            {
                "layout_slug": "photo_story",
                "variant_name": "image_present",
                "build_success": True,
                "overflow": False,
                "placeholder_empty": False,
                "image_missing": False,
                "font_too_small": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_script("--suite-dir", str(suite_dir), "--output", str(output_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] == 2
    assert payload["failed"] == 0
    assert payload["coverage_pct"] == 100.0


def test_build_coverage_matrix_flags_missing_variants_for_testable_layouts(tmp_path: Path) -> None:
    module = _load_script_module()
    suite_dir = tmp_path / "cert-suite" / "sparse-template"
    suite_dir.mkdir(parents=True)
    inventory = {
        "layouts": [
            {
                "slug": "title_only",
                "usable": True,
                "testable": True,
                "requires_image": False,
                "slot_structure": "heading_only",
                "exclude_reason": None,
            }
        ]
    }

    payload = module.build_coverage_matrix(
        inventory,
        suite_dir=suite_dir,
        output_path=tmp_path / "runs" / "run-003" / "coverage.json",
    )

    assert payload["passed"] == 0
    assert payload["failed"] == 1
    assert payload["coverage_pct"] == 0.0
    assert payload["layouts"][0]["failure_reasons"] == ["no variants evaluated"]
