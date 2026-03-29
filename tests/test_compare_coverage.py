from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "compare_coverage.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("compare_coverage", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_coverage(path: Path, *, template: str, layouts: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"template": template, "layouts": layouts}, indent=2) + "\n",
        encoding="utf-8",
    )


def test_compare_coverage_detects_regressions_improvements_and_new_layouts(tmp_path: Path) -> None:
    module = _load_script_module()
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write_coverage(
        before_path,
        template="bcg",
        layouts=[
            {"slug": "title_only", "variants_passed": 2},
            {"slug": "image_left", "variants_passed": 0},
            {"slug": "quote", "variants_passed": 1},
            {"slug": "gallery", "variants_passed": 0},
        ],
    )
    _write_coverage(
        after_path,
        template="bcg",
        layouts=[
            {"slug": "title_only", "variants_passed": 0},
            {"slug": "image_left", "variants_passed": 1},
            {"slug": "quote", "variants_passed": 3},
            {"slug": "hero_image", "variants_passed": 1},
        ],
    )

    diff = module.compare_coverage_files(before_path=before_path, after_path=after_path)

    assert diff["regressions"] == [{"slug": "title_only", "before_passed": 2, "after_passed": 0}]
    assert diff["improvements"] == [
        {"slug": "image_left", "before_passed": 0, "after_passed": 1},
        {"slug": "quote", "before_passed": 1, "after_passed": 3},
    ]
    assert diff["new_layouts"] == [{"slug": "hero_image", "before_passed": 0, "after_passed": 1}]
    assert diff["unchanged"] == [
        {"slug": "gallery", "before_passed": 0, "after_passed": 0},
    ]


def test_compare_coverage_script_exit_code_reflects_regressions(tmp_path: Path) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write_coverage(
        before_path,
        template="bcg",
        layouts=[{"slug": "title_only", "variants_passed": 1}],
    )
    _write_coverage(
        after_path,
        template="bcg",
        layouts=[{"slug": "title_only", "variants_passed": 0}],
    )

    result = _run_script("--before", str(before_path), "--after", str(after_path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["regressions"] == [{"slug": "title_only", "before_passed": 1, "after_passed": 0}]


def test_compare_coverage_script_exits_zero_without_regressions(tmp_path: Path) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write_coverage(
        before_path,
        template="bcg",
        layouts=[{"slug": "title_only", "variants_passed": 0}],
    )
    _write_coverage(
        after_path,
        template="bcg",
        layouts=[
            {"slug": "title_only", "variants_passed": 1},
            {"slug": "hero_image", "variants_passed": 1},
        ],
    )

    result = _run_script("--before", str(before_path), "--after", str(after_path))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["regressions"] == []
    assert payload["improvements"] == [{"slug": "title_only", "before_passed": 0, "after_passed": 1}]
    assert payload["new_layouts"] == [{"slug": "hero_image", "before_passed": 0, "after_passed": 1}]
