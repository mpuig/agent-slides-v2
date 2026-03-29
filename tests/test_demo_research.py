from __future__ import annotations

import importlib.util
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


def _image_node(node_id: str, slot_binding: str = "image", image_path: str | None = None) -> dict:
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
- Use **title**, **hero_image**, **comparison**, and **closing** exactly once.
- For **hero_image** and **image_right**, fill the image slot with a real image.
- For **comparison** and **two_col**, keep headings short because the columns are narrow.
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
        if command == "review":
            return {"ok": True, "data": {"overall_grade": "A", "slides": len(slides)}}
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(module, "run_cli", fake_run_cli)

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
        _slide("closing", [_text_node("n-4", "body", "Thank you")]),
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
        if command == "review":
            return {"ok": True, "data": {"overall_grade": "B", "slides": len(slides)}}
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(module, "run_cli", fake_run_cli)

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


def test_score_deck_lists_five_missing_required_layouts(tmp_path: Path, monkeypatch) -> None:
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
        _slide("title", [_text_node("n-1", "heading", "Only one required layout present")]),
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
        if command == "review":
            return {"ok": True, "data": {"overall_grade": "B", "slides": len(slides)}}
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(module, "run_cli", fake_run_cli)

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
        if command == "review":
            return {"ok": True, "data": {"overall_grade": "A", "slides": len(slides)}}
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(module, "run_cli", fake_run_cli)

    scores = module.score_deck(deck_path, brief, run_dir)

    assert scores["layout_coverage"] == 1.0
    assert scores["layout_variety"] == 1.0
    assert scores["brief_compliance"]["required_layouts_missing"] == []
