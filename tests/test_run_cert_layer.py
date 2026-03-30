from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_cert_layer.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_cert_layer", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_template_pipeline_orchestrates_cert_steps(tmp_path: Path, monkeypatch) -> None:
    module = _load_script_module()
    template_path = tmp_path / "examples" / "brand-template.pptx"
    template_path.parent.mkdir(parents=True)
    template_path.write_bytes(b"pptx")
    run_dir = tmp_path / "runs" / "run-001"
    call_order: list[str] = []

    class LearnResult:
        manifest = {"source": "../examples/brand-template.pptx"}

    def fake_read_template_manifest(path: Path, output_path: Path):
        assert path == template_path
        assert output_path == run_dir / "certification" / "brand-template" / "manifest.json"
        call_order.append("learn")
        return LearnResult()

    def fake_write_inventory(manifest: dict[str, object], output_path: Path) -> dict[str, object]:
        assert manifest == LearnResult.manifest
        assert output_path == run_dir / "certification" / "brand-template" / "inventory.json"
        call_order.append("inventory")
        return {"layouts": [{"slug": "title", "testable": True}]}

    def fake_build_fixture_payloads(inventory: dict[str, object]) -> dict[str, object]:
        assert inventory == {"layouts": [{"slug": "title", "testable": True}]}
        call_order.append("fixtures")
        return {"heading_only": {"nominal": {"heading": {"blocks": []}}}}

    def fake_write_fixture_payloads(payloads: dict[str, object], output_dir: Path) -> list[Path]:
        assert output_dir == run_dir / "certification" / "brand-template" / "fixtures"
        call_order.append("write_fixtures")
        return [output_dir / "heading_only.json"]

    def fake_build_cert_suite(
        manifest_path: Path,
        inventory: dict[str, object],
        fixture_payloads: dict[str, object],
        *,
        output_dir: Path,
    ) -> list[Path]:
        assert manifest_path == run_dir / "certification" / "brand-template" / "manifest.json"
        assert output_dir == run_dir / "certification" / "brand-template" / "suite"
        call_order.append("suite")
        deck_path = output_dir / "brand-template" / "title" / "nominal" / "deck.json"
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        deck_path.write_text("{}", encoding="utf-8")
        return [deck_path]

    def fake_build_deck_artifacts(deck_path: Path) -> dict[str, object]:
        call_order.append("build_deck")
        return {"deck_path": str(deck_path), "build_success": True}

    def fake_build_coverage_matrix(*, suite_dir: Path, output_path: Path) -> dict[str, object]:
        assert suite_dir == run_dir / "certification" / "brand-template" / "suite" / "brand-template"
        assert output_path == run_dir / "certification" / "brand-template" / "coverage.json"
        call_order.append("coverage")
        return {"template": "brand-template", "testable": 4, "coverage_pct": 100.0}

    monkeypatch.setattr(module, "read_template_manifest", fake_read_template_manifest)
    monkeypatch.setattr(module, "_write_inventory", fake_write_inventory)
    monkeypatch.setattr(module, "build_fixture_payloads", fake_build_fixture_payloads)
    monkeypatch.setattr(module, "write_fixture_payloads", fake_write_fixture_payloads)
    monkeypatch.setattr(module, "build_cert_suite", fake_build_cert_suite)
    monkeypatch.setattr(module, "build_deck_artifacts", fake_build_deck_artifacts)
    monkeypatch.setattr(module, "build_coverage_matrix", fake_build_coverage_matrix)

    result = module.run_template_pipeline(template_path=template_path, run_dir=run_dir)

    assert call_order == [
        "learn",
        "inventory",
        "fixtures",
        "write_fixtures",
        "suite",
        "build_deck",
        "coverage",
    ]
    assert result["template"] == "brand-template"
    assert result["coverage_pct"] == 100.0
    assert result["coverage_path"] == "certification/brand-template/coverage.json"
    assert result["deck_count"] == 1


def test_build_layer_summary_applies_per_template_regression_gate(tmp_path: Path, monkeypatch) -> None:
    module = _load_script_module()
    runs_dir = tmp_path / "runs"
    baseline_dir = runs_dir / "baseline"
    candidate_dir = runs_dir / "candidate"
    baseline_dir.mkdir(parents=True)
    candidate_dir.mkdir(parents=True)

    (baseline_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "baseline",
                "layers": {
                    "certification": {
                        "decision": "accept",
                        "overall_coverage_pct": 95.0,
                        "templates": [
                            {"template": "alpha", "coverage_path": "certification/alpha/coverage.json"},
                            {"template": "beta", "coverage_path": "certification/beta/coverage.json"},
                        ],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (baseline_dir / "certification" / "alpha").mkdir(parents=True)
    (baseline_dir / "certification" / "beta").mkdir(parents=True)
    (candidate_dir / "certification" / "alpha").mkdir(parents=True)
    (candidate_dir / "certification" / "beta").mkdir(parents=True)

    (baseline_dir / "certification" / "alpha" / "coverage.json").write_text(
        json.dumps({"template": "alpha", "layouts": [{"slug": "hero", "variants_passed": 1}]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (baseline_dir / "certification" / "beta" / "coverage.json").write_text(
        json.dumps({"template": "beta", "layouts": [{"slug": "title", "variants_passed": 1}]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (candidate_dir / "certification" / "alpha" / "coverage.json").write_text(
        json.dumps({"template": "alpha", "layouts": [{"slug": "hero", "variants_passed": 0}]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (candidate_dir / "certification" / "beta" / "coverage.json").write_text(
        json.dumps({"template": "beta", "layouts": [{"slug": "title", "variants_passed": 1}]}, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "RUNS_DIR", runs_dir)

    layer = module.build_layer_summary(
        run_id="candidate",
        templates=[
            {"template": "alpha", "coverage_pct": 80.0, "passed": 4, "testable": 5, "coverage_path": "certification/alpha/coverage.json"},
            {"template": "beta", "coverage_pct": 100.0, "passed": 5, "testable": 5, "coverage_path": "certification/beta/coverage.json"},
        ],
    )

    assert layer["overall_coverage_pct"] == 90.0
    assert layer["decision"] == "reject"
    assert layer["reject_reasons"][0] == "coverage regressed from 95.0 to 90.0"
    assert "alpha: layout regressions: hero" in layer["reject_reasons"][1]


def test_main_updates_top_level_summary_without_overwriting_demo_layer(tmp_path: Path, monkeypatch) -> None:
    module = _load_script_module()
    runs_dir = tmp_path / "runs"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    run_id = "run-123"

    templates = [examples_dir / "one.pptx", examples_dir / "two.pptx", examples_dir / "three.pptx"]
    for template in templates:
        template.write_bytes(b"pptx")

    existing_summary_dir = runs_dir / run_id
    existing_summary_dir.mkdir(parents=True)
    (existing_summary_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "layers": {
                    "demo": {
                        "mean_composite": 81.0,
                        "review_quality": 0.9,
                        "decision": "accept",
                        "reject_reasons": [],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_run_template_pipeline(*, template_path: Path, run_dir: Path) -> dict[str, object]:
        return {
            "template": template_path.stem,
            "coverage_pct": 100.0,
            "passed": 5,
            "testable": 5,
            "coverage_path": f"certification/{template_path.stem}/coverage.json",
        }

    def fake_certification_summary_path_for(target_run_id: str) -> Path:
        return runs_dir / target_run_id / "certification" / "summary.json"

    def fake_update_run_summary(
        target_run_id: str,
        *,
        layer_name: str,
        layer_payload: dict[str, object],
        top_level_updates: dict[str, object] | None = None,
    ) -> dict[str, object]:
        summary_path = runs_dir / target_run_id / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.setdefault("layers", {})[layer_name] = layer_payload
        if top_level_updates:
            summary.update(top_level_updates)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary

    monkeypatch.setattr(module, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(module, "discover_example_templates", lambda path: templates)
    monkeypatch.setattr(module, "run_template_pipeline", fake_run_template_pipeline)
    monkeypatch.setattr(module, "certification_summary_path_for", fake_certification_summary_path_for)
    monkeypatch.setattr(module, "update_run_summary", fake_update_run_summary)

    exit_code = module.main(["--run-id", run_id, "--examples-dir", str(examples_dir)])

    assert exit_code == 0
    summary = json.loads((runs_dir / run_id / "summary.json").read_text(encoding="utf-8"))
    assert summary["layers"]["demo"]["mean_composite"] == 81.0
    assert summary["layers"]["certification"]["overall_coverage_pct"] == 100.0
    certification_summary = json.loads((runs_dir / run_id / "certification" / "summary.json").read_text(encoding="utf-8"))
    assert certification_summary["layer"] == "certification"
    assert len(certification_summary["templates"]) == 3
