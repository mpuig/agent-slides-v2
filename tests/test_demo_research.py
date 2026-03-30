from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "demo_research.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("demo_research", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text_node(node_id: str, slot_binding: str, text: str) -> dict:
    return {
        "node_id": node_id,
        "slot_binding": slot_binding,
        "type": "text",
        "content": {"blocks": [{"type": "paragraph", "text": text}]},
    }


def _image_node(
    node_id: str, slot_binding: str = "image", image_path: str | None = None
) -> dict:
    node = {
        "node_id": node_id,
        "slot_binding": slot_binding,
        "type": "image",
    }
    if image_path is not None:
        node["image_path"] = image_path
    return node


def _slide(layout: str, nodes: list[dict]) -> dict:
    return {
        "layout": layout,
        "nodes": nodes,
        "computed": {node["node_id"]: {} for node in nodes},
    }


def _brief() -> dict[str, int]:
    return {"min_slides": 1, "max_slides": 1, "min_layouts": 1}


def _info_payload() -> dict[str, object]:
    return {
        "slides": [
            {
                "layout": "title",
                "computed": {"n-1": {}},
                "nodes": [
                    {
                        "node_id": "n-1",
                        "slot_binding": "heading",
                        "type": "text",
                        "content": {"blocks": [{"text": "Hello"}]},
                    }
                ],
            }
        ]
    }


def test_parse_brief_extracts_structured_requirements(tmp_path: Path) -> None:
    module = _load_script_module()
    brief_path = tmp_path / "layout-showcase.md"
    brief_path.write_text(
        """# Layout Showcase

## Template
examples/bcg.pptx

## Expected slide count
20

## Layout variety
1. **title** — use exactly once as opener.
2. **hero_image** — fill the image slot with a real image.
3. **comparison** — keep headings short because the columns are narrow.
4. **closing** — use exactly once as closer.
5. **image_right** — fill the image slot with a real image.
6. **two_col** — keep headings short because the columns are narrow.
- At least 3 slides should include a source line.
""",
        encoding="utf-8",
    )

    parsed = module.parse_brief(brief_path)

    assert parsed["required_layouts"] == [
        "title",
        "hero_image",
        "comparison",
        "closing",
        "image_right",
        "two_col",
    ]
    assert parsed["image_required_layouts"] == ["hero_image", "image_right"]
    assert parsed["narrow_layouts"] == ["comparison", "two_col"]
    assert parsed["min_source_lines"] == 3
    assert parsed["min_slides"] == 20
    assert parsed["max_slides"] == 20


def test_score_deck_reports_brief_compliance_and_required_layout_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"png")

    brief = {
        "required_layouts": ["title", "image_right", "comparison", "closing"],
        "image_required_layouts": ["image_right"],
        "narrow_layouts": ["comparison"],
        "min_source_lines": 2,
        "min_slides": 4,
        "max_slides": 4,
    }

    slides = [
        _slide("title", [_text_node("n-1", "heading", "Quarterly update")]),
        _slide(
            "image_right",
            [
                _text_node("n-2", "heading", "Growth snapshot"),
                _text_node("n-3", "body", "Revenue up 18%"),
                _image_node("n-4", image_path="photo.png"),
                _text_node("n-5", "source", "Source: IDC 2026"),
            ],
        ),
        _slide(
            "comparison",
            [
                _text_node("n-6", "heading", "Trade-offs"),
                _text_node("n-7", "col1", "Build"),
                _text_node("n-8", "col2", "Buy"),
                _text_node("n-9", "source", "Source: Internal analysis"),
            ],
        ),
        _slide("closing", [_text_node("n-10", "body", "Approve phase one")]),
    ]

    def fake_run_cli(*args: str, cwd: Path | None = None):
        command = args[0]
        if command == "build":
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_bytes(b"pptx")
            return {"ok": True}
        if command == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if command == "info":
            return {"slides": slides}
        raise AssertionError(f"Unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            0,
            {
                "ok": True,
                "data": {
                    "overall_grade": "A",
                    "slides": len(slides),
                },
            },
            None,
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, brief, run_dir)

    assert scores["layout_coverage"] == 1.0
    assert scores["layout_variety"] == 1.0
    assert scores["placeholder_fill"] == 1.0
    assert scores["brief_compliance"] == {
        "required_layouts_present": ["title", "image_right", "comparison", "closing"],
        "required_layouts_missing": [],
        "image_layouts_filled": 1,
        "image_layouts_expected": 1,
        "image_files_valid": True,
        "narrow_headings_ok": True,
        "source_lines_found": 2,
    }
    assert scores["composite"] == 100.0


def test_score_deck_penalizes_missing_required_layouts_and_invalid_images(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    brief = {
        "required_layouts": [
            "title",
            "hero_image",
            "comparison",
            "image_right",
            "two_col",
            "closing",
        ],
        "image_required_layouts": ["hero_image", "image_right"],
        "narrow_layouts": ["comparison"],
        "min_source_lines": 1,
        "min_slides": 3,
        "max_slides": 6,
    }

    slides = [
        _slide("title", [_text_node("n-1", "heading", "Title")]),
        _slide(
            "hero_image",
            [
                _text_node("n-2", "heading", "Hero image"),
                _image_node("n-3", image_path="missing-photo.png"),
            ],
        ),
        _slide(
            "comparison",
            [
                _text_node("n-4", "heading", "This heading is definitely too long"),
                _text_node("n-5", "col1", "Option A"),
                _text_node("n-6", "col2", "Option B"),
            ],
        ),
        _slide("closing", [_text_node("n-7", "body", "Thank you")]),
    ]

    def fake_run_cli(*args: str, cwd: Path | None = None):
        command = args[0]
        if command == "build":
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_bytes(b"pptx")
            return {"ok": True}
        if command == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if command == "info":
            return {"slides": slides}
        raise AssertionError(f"Unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            0,
            {
                "ok": True,
                "data": {
                    "overall_grade": "B",
                    "slides": len(slides),
                },
            },
            None,
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, brief, run_dir)

    assert scores["layout_coverage"] == 4 / 6
    assert scores["brief_compliance"]["required_layouts_missing"] == [
        "image_right",
        "two_col",
    ]
    assert scores["brief_compliance"]["image_layouts_expected"] == 2
    assert scores["brief_compliance"]["image_layouts_filled"] == 0
    assert scores["brief_compliance"]["image_files_valid"] is False
    assert scores["brief_compliance"]["narrow_headings_ok"] is False
    assert scores["brief_compliance"]["source_lines_found"] == 0
    assert scores["placeholder_fill"] == 0.0
    assert scores["composite"] == 0.0


def test_score_deck_lists_five_missing_required_layouts(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    brief = {
        "required_layouts": [
            "title",
            "hero_image",
            "comparison",
            "image_right",
            "two_col",
            "closing",
        ],
        "image_required_layouts": [],
        "narrow_layouts": [],
        "min_source_lines": 0,
        "min_slides": 1,
        "max_slides": 6,
    }

    slides = [
        _slide(
            "title", [_text_node("n-1", "heading", "Only one required layout present")]
        ),
    ]

    def fake_run_cli(*args: str, cwd: Path | None = None):
        command = args[0]
        if command == "build":
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_bytes(b"pptx")
            return {"ok": True}
        if command == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if command == "info":
            return {"slides": slides}
        raise AssertionError(f"Unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            0,
            {
                "ok": True,
                "data": {
                    "overall_grade": "B",
                    "slides": len(slides),
                },
            },
            None,
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, brief, run_dir)

    assert scores["layout_coverage"] == 1 / 6
    assert scores["brief_compliance"]["required_layouts_missing"] == [
        "hero_image",
        "comparison",
        "image_right",
        "two_col",
        "closing",
    ]


def test_score_deck_falls_back_to_generic_layout_scoring_without_required_layouts(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    brief = {
        "min_layouts": 3,
        "min_slides": 3,
        "max_slides": 3,
        "required_layouts": [],
        "image_required_layouts": [],
        "narrow_layouts": [],
        "min_source_lines": 0,
    }

    slides = [
        _slide("title", [_text_node("n-1", "heading", "Title")]),
        _slide("two_col", [_text_node("n-2", "heading", "Split view")]),
        _slide("closing", [_text_node("n-3", "body", "Done")]),
    ]

    def fake_run_cli(*args: str, cwd: Path | None = None):
        command = args[0]
        if command == "build":
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_bytes(b"pptx")
            return {"ok": True}
        if command == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if command == "info":
            return {"slides": slides}
        raise AssertionError(f"Unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            0,
            {
                "ok": True,
                "data": {
                    "overall_grade": "A",
                    "slides": len(slides),
                },
            },
            None,
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, brief, run_dir)

    assert scores["layout_coverage"] == 1.0
    assert scores["layout_variety"] == 1.0
    assert scores["brief_compliance"]["required_layouts_missing"] == []


def test_score_deck_records_review_quality_from_report_ratio(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")
    report_json_path = tmp_path / "review-report.json"
    report_json_path.write_text(
        json.dumps({"active": {"overall": {"grade": "B", "passed": 8, "total": 10}}}),
        encoding="utf-8",
    )

    def fake_run_cli(*args: str, cwd: Path | None = None) -> dict[str, object] | None:
        if args[0] == "build":
            Path(args[3]).write_bytes(b"pptx")
            return {"ok": True}
        if args[0] == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if args[0] == "info":
            return _info_payload()
        raise AssertionError(f"unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            0,
            {
                "ok": True,
                "data": {
                    "overall_grade": "B",
                    "slides": 1,
                    "report_json_path": str(report_json_path),
                },
            },
            None,
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, _brief(), tmp_path)

    assert scores["review_available"] is True
    assert scores["review_passed"] == 8
    assert scores["review_total"] == 10
    assert scores["review_quality"] == 0.8
    assert scores["composite"] == 96.7


def test_score_deck_excludes_unavailable_review_from_composite(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script_module()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")

    def fake_run_cli(*args: str, cwd: Path | None = None) -> dict[str, object] | None:
        if args[0] == "build":
            Path(args[3]).write_bytes(b"pptx")
            return {"ok": True}
        if args[0] == "validate":
            return {"ok": True, "data": {"warnings": []}}
        if args[0] == "info":
            return _info_payload()
        raise AssertionError(f"unexpected command: {args}")

    def fake_invoke_cli(
        *args: str,
        cwd: Path | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, object] | None]:
        assert args[0] == "review"
        return (
            1,
            None,
            {
                "error": {
                    "message": "Visual review requires 'soffice' to be installed and available on PATH."
                }
            },
        )

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    monkeypatch.setattr(module, "invoke_cli", fake_invoke_cli)

    scores = module.score_deck(deck_path, _brief(), tmp_path)

    assert scores["review_available"] is False
    assert scores["review_quality"] == 0.0
    assert scores["review_passed"] == 0
    assert scores["review_total"] == 0
    assert "soffice" in scores["review_error"]
    assert scores["composite"] == 100.0


def test_run_benchmark_without_deck_still_writes_review_fields(tmp_path: Path) -> None:
    module = _load_script_module()
    brief_path = tmp_path / "minimal.md"
    brief_path.write_text(
        "# Minimal\n\n## Expected slide count\n1\n\n## Layout variety\nAt least 1 distinct layout\n",
        encoding="utf-8",
    )

    result = module.run_benchmark(brief_path, tmp_path / "runs")

    scores = result["scores"]
    assert scores["review_available"] is False
    assert scores["review_quality"] == 0.0
    assert scores["review_passed"] == 0
    assert scores["review_total"] == 0


def test_build_summary_rejects_review_regressions_even_when_composite_improves(
    monkeypatch,
) -> None:
    module = _load_script_module()
    previous = {
        "run_id": "baseline",
        "mean_composite": 80.0,
        "benchmarks": [
            {
                "benchmark": "alpha",
                "scores": {
                    "composite": 80.0,
                    "review_available": True,
                    "review_quality": 0.92,
                },
            },
            {
                "benchmark": "beta",
                "scores": {
                    "composite": 78.0,
                    "review_available": True,
                    "review_quality": 0.88,
                },
            },
        ],
    }
    results = [
        {
            "benchmark": "alpha",
            "scores": {
                "composite": 83.0,
                "review_available": True,
                "review_quality": 0.84,
            },
        },
        {
            "benchmark": "beta",
            "scores": {
                "composite": 82.0,
                "review_available": True,
                "review_quality": 0.8,
            },
        },
    ]

    monkeypatch.setattr(
        module, "previous_best_summary", lambda current_run_id: previous
    )

    summary = module.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "reject"
    assert len(summary["reject_reasons"]) == 2
    assert "alpha: review_quality regressed" in summary["reject_reasons"][0]
    assert "beta: review_quality regressed" in summary["reject_reasons"][1]
    assert summary["layers"]["demo"]["mean_composite"] == 82.5
    assert summary["layers"]["demo"]["review_quality"] == 0.82


def test_build_summary_rejects_composite_regression_even_when_review_improves(
    monkeypatch,
) -> None:
    module = _load_script_module()
    previous = {
        "run_id": "baseline",
        "mean_composite": 81.0,
        "benchmarks": [
            {
                "benchmark": "alpha",
                "scores": {
                    "composite": 81.0,
                    "review_available": True,
                    "review_quality": 0.7,
                },
            }
        ],
    }
    results = [
        {
            "benchmark": "alpha",
            "scores": {
                "composite": 79.0,
                "review_available": True,
                "review_quality": 0.95,
            },
        }
    ]

    monkeypatch.setattr(
        module, "previous_best_summary", lambda current_run_id: previous
    )

    summary = module.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "reject"
    assert summary["reject_reasons"] == ["composite regressed from 81.0 to 79.0"]
    assert summary["layers"]["demo"]["decision"] == "reject"


def test_build_summary_uses_layered_demo_baseline(monkeypatch) -> None:
    module = _load_script_module()
    previous = {
        "run_id": "baseline",
        "layers": {
            "demo": {
                "mean_composite": 75.0,
                "decision": "accept",
            }
        },
        "benchmarks": [
            {
                "benchmark": "alpha",
                "scores": {
                    "composite": 75.0,
                    "review_available": True,
                    "review_quality": 0.9,
                },
            }
        ],
    }
    results = [
        {
            "benchmark": "alpha",
            "scores": {
                "composite": 80.0,
                "review_available": True,
                "review_quality": 0.92,
            },
        }
    ]
    monkeypatch.setattr(
        module, "previous_best_summary", lambda current_run_id: previous
    )

    summary = module.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "accept"
    assert summary["previous_best_mean_composite"] == 75.0
    assert summary["layers"]["demo"]["decision"] == "accept"


def test_build_summary_rejects_when_baseline_had_review_but_current_does_not(
    monkeypatch,
) -> None:
    module = _load_script_module()
    previous = {
        "run_id": "baseline",
        "mean_composite": 80.0,
        "benchmarks": [
            {
                "benchmark": "alpha",
                "scores": {
                    "composite": 80.0,
                    "review_available": True,
                    "review_quality": 0.85,
                },
            }
        ],
    }
    results = [
        {
            "benchmark": "alpha",
            "scores": {
                "composite": 85.0,
                "review_available": False,
                "review_quality": 0.0,
            },
        }
    ]

    monkeypatch.setattr(
        module, "previous_best_summary", lambda current_run_id: previous
    )

    summary = module.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "reject"
    assert any("review data lost" in r for r in summary["reject_reasons"])


def test_build_summary_does_not_include_certification_regression_fields(
    monkeypatch,
) -> None:
    module = _load_script_module()
    previous = {
        "run_id": "baseline",
        "mean_composite": 75.0,
        "benchmarks": [
            {
                "benchmark": "alpha",
                "scores": {
                    "composite": 75.0,
                    "review_available": True,
                    "review_quality": 0.9,
                },
            }
        ],
    }
    results = [
        {
            "benchmark": "alpha",
            "scores": {
                "composite": 80.0,
                "review_available": True,
                "review_quality": 0.92,
            },
        }
    ]
    monkeypatch.setattr(
        module, "previous_best_summary", lambda current_run_id: previous
    )

    summary = module.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "accept"
    assert summary["reject_reasons"] == []
    assert "coverage_diff" not in summary
    assert summary["layers"]["demo"]["review_quality"] == 0.92
