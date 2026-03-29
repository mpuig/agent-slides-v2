from __future__ import annotations

import json
from pathlib import Path

from scripts import demo_research


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


def test_score_deck_records_review_quality_from_report_ratio(tmp_path: Path, monkeypatch) -> None:
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

    monkeypatch.setattr(demo_research, "run_cli", fake_run_cli)
    monkeypatch.setattr(demo_research, "invoke_cli", fake_invoke_cli)

    scores = demo_research.score_deck(deck_path, _brief(), tmp_path)

    assert scores["review_available"] is True
    assert scores["review_passed"] == 8
    assert scores["review_total"] == 10
    assert scores["review_quality"] == 0.8
    assert scores["composite"] == 96.7


def test_score_deck_excludes_unavailable_review_from_composite(tmp_path: Path, monkeypatch) -> None:
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
            {"error": {"message": "Visual review requires 'soffice' to be installed and available on PATH."}},
        )

    monkeypatch.setattr(demo_research, "run_cli", fake_run_cli)
    monkeypatch.setattr(demo_research, "invoke_cli", fake_invoke_cli)

    scores = demo_research.score_deck(deck_path, _brief(), tmp_path)

    assert scores["review_available"] is False
    assert scores["review_quality"] == 0.0
    assert scores["review_passed"] == 0
    assert scores["review_total"] == 0
    assert "soffice" in scores["review_error"]
    assert scores["composite"] == 100.0


def test_run_benchmark_without_deck_still_writes_review_fields(tmp_path: Path) -> None:
    brief_path = tmp_path / "minimal.md"
    brief_path.write_text(
        "# Minimal\n\n## Expected slide count\n1\n\n## Layout variety\nAt least 1 distinct layout\n",
        encoding="utf-8",
    )

    result = demo_research.run_benchmark(brief_path, tmp_path / "runs")

    scores = result["scores"]
    assert scores["review_available"] is False
    assert scores["review_quality"] == 0.0
    assert scores["review_passed"] == 0
    assert scores["review_total"] == 0


def test_build_summary_rejects_review_regressions_even_when_composite_improves(monkeypatch) -> None:
    previous = {
        "run_id": "baseline",
        "mean_composite": 80.0,
        "benchmarks": [
            {"benchmark": "alpha", "scores": {"composite": 80.0, "review_available": True, "review_quality": 0.92}},
            {"benchmark": "beta", "scores": {"composite": 78.0, "review_available": True, "review_quality": 0.88}},
        ],
    }
    results = [
        {"benchmark": "alpha", "scores": {"composite": 83.0, "review_available": True, "review_quality": 0.84}},
        {"benchmark": "beta", "scores": {"composite": 82.0, "review_available": True, "review_quality": 0.8}},
    ]

    monkeypatch.setattr(demo_research, "previous_best_summary", lambda current_run_id: previous)

    summary = demo_research.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "reject"
    assert len(summary["reject_reasons"]) == 2
    assert "alpha: review_quality regressed" in summary["reject_reasons"][0]
    assert "beta: review_quality regressed" in summary["reject_reasons"][1]


def test_build_summary_rejects_composite_regression_even_when_review_improves(monkeypatch) -> None:
    previous = {
        "run_id": "baseline",
        "mean_composite": 81.0,
        "benchmarks": [
            {"benchmark": "alpha", "scores": {"composite": 81.0, "review_available": True, "review_quality": 0.7}}
        ],
    }
    results = [
        {"benchmark": "alpha", "scores": {"composite": 79.0, "review_available": True, "review_quality": 0.95}}
    ]

    monkeypatch.setattr(demo_research, "previous_best_summary", lambda current_run_id: previous)

    summary = demo_research.build_summary(run_id="candidate", results=results)

    assert summary["decision"] == "reject"
    assert summary["reject_reasons"] == ["composite regressed from 81.0 to 79.0"]
