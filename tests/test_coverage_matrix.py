from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from agent_slides.model import ComputedDeck, ComputedNode, Counters, Deck, Node, Slide

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_coverage_matrix.py"


def _load_script_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_deck(path: Path, deck: Deck) -> None:
    payload = deck.model_dump(mode="json", by_alias=True, exclude_none=True)
    for slide in payload["slides"]:
        slide.pop("revision", None)
        slide.pop("computed", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_computed_sidecar(path: Path, deck: Deck) -> None:
    computed_path = path.with_name(f"{path.stem}.computed{path.suffix}")
    computed_path.write_text(ComputedDeck.from_deck(deck).model_dump_json(indent=2, exclude_none=True) + "\n")


def _write_scores(path: Path, *, build_success: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"build_success": build_success}, indent=2) + "\n", encoding="utf-8")


def test_generate_coverage_matrix_reports_pass_fail_and_exclusions(tmp_path: Path) -> None:
    module = _load_script_module(SCRIPT_PATH, "generate_coverage_matrix")
    suite_dir = tmp_path / "cert-suite" / "brand-template"
    run_dir = tmp_path / "runs" / "run-001"
    output_path = run_dir / "coverage.json"

    inventory = {
        "layouts": [
            {
                "slug": "image_left",
                "usable": True,
                "testable": True,
                "requires_image": True,
                "slot_structure": "heading_body_image",
                "fillable_slots": ["heading", "body", "image"],
                "exclude_reason": None,
            },
            {
                "slug": "title_content",
                "usable": True,
                "testable": True,
                "requires_image": False,
                "slot_structure": "heading_body",
                "fillable_slots": ["heading", "body"],
                "exclude_reason": None,
            },
            {
                "slug": "quote",
                "usable": True,
                "testable": False,
                "requires_image": False,
                "slot_structure": "heading_only",
                "fillable_slots": ["quote"],
                "exclude_reason": "manual review only",
            },
        ]
    }
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    image_pass_deck = Deck(
        deck_id="image-pass",
        slides=[
            Slide(
                slide_id="s-1",
                layout="image_left",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Heading"),
                    Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
                    Node(node_id="n-3", slot_binding="image", type="image", content={"blocks": []}, image_path="hero.png"),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=3),
    )
    image_fail_deck = Deck(
        deck_id="image-fail",
        slides=[
            Slide(
                slide_id="s-1",
                layout="image_left",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Heading"),
                    Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )
    text_fail_deck = Deck(
        deck_id="text-fail",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Heading"),
                    Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=0.0,
                        y=0.0,
                        width=100.0,
                        height=20.0,
                        font_size_pt=24.0,
                        font_family="Aptos",
                        revision=1,
                    ),
                    "n-2": ComputedNode(
                        x=0.0,
                        y=20.0,
                        width=100.0,
                        height=80.0,
                        font_size_pt=7.0,
                        font_family="Aptos",
                        revision=1,
                        text_overflow=True,
                    ),
                },
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )

    image_pass_path = suite_dir / "image_left" / "nominal" / "deck.json"
    image_fail_path = suite_dir / "image_left" / "image_missing" / "deck.json"
    text_fail_path = suite_dir / "title_content" / "overflow" / "deck.json"
    _write_deck(image_pass_path, image_pass_deck)
    _write_deck(image_fail_path, image_fail_deck)
    _write_deck(text_fail_path, text_fail_deck)
    _write_computed_sidecar(text_fail_path, text_fail_deck)

    _write_scores(run_dir / "brand-template" / "image_left" / "nominal" / "scores.json", build_success=1.0)
    _write_scores(run_dir / "brand-template" / "image_left" / "image_missing" / "scores.json", build_success=1.0)
    _write_scores(run_dir / "brand-template" / "title_content" / "overflow" / "scores.json", build_success=1.0)

    exit_code = module.main(["--suite-dir", str(suite_dir), "--output", str(output_path)])

    assert exit_code == 1
    coverage = json.loads(output_path.read_text(encoding="utf-8"))
    assert coverage["template"] == "brand-template"
    assert coverage["run_id"] == "run-001"
    assert coverage["total_layouts"] == 3
    assert coverage["usable"] == 3
    assert coverage["testable"] == 2
    assert coverage["excluded"] == [{"slug": "quote", "reason": "manual review only"}]
    assert coverage["passed"] == 1
    assert coverage["failed"] == 1
    assert coverage["coverage_pct"] == 50.0

    layouts = {layout["slug"]: layout for layout in coverage["layouts"]}
    assert layouts["quote"]["status"] == "excluded"

    assert layouts["image_left"]["status"] == "pass"
    assert layouts["image_left"]["variants_tested"] == 2
    assert layouts["image_left"]["variants_passed"] == 1
    assert layouts["image_left"]["variants_failed"] == 1
    assert layouts["image_left"]["failure_reasons"] == ["image_missing", "placeholder_empty"]

    image_variants = {variant["variant_name"]: variant for variant in layouts["image_left"]["variants"]}
    assert image_variants["nominal"]["pass"] is True
    assert image_variants["nominal"]["build_success"] is True
    assert image_variants["image_missing"]["placeholder_empty"] is True
    assert image_variants["image_missing"]["image_missing"] is True
    assert image_variants["image_missing"]["pass"] is False

    assert layouts["title_content"]["status"] == "fail"
    assert layouts["title_content"]["variants_tested"] == 1
    assert layouts["title_content"]["variants_passed"] == 0
    assert layouts["title_content"]["variants_failed"] == 1
    assert layouts["title_content"]["failure_reasons"] == ["font_too_small", "overflow"]
    assert layouts["title_content"]["variants"][0]["overflow"] is True
    assert layouts["title_content"]["variants"][0]["font_too_small"] is True


def test_generate_coverage_matrix_prefers_render_oracle_signals_when_available(tmp_path: Path) -> None:
    module = _load_script_module(SCRIPT_PATH, "generate_coverage_matrix")
    suite_dir = tmp_path / "cert-suite" / "brand-template"
    run_dir = tmp_path / "runs" / "run-002"
    output_path = run_dir / "coverage.json"

    inventory = {
        "layouts": [
            {
                "slug": "title_content",
                "usable": True,
                "testable": True,
                "requires_image": False,
                "slot_structure": "heading_body",
                "fillable_slots": ["heading", "body"],
                "exclude_reason": None,
            }
        ]
    }
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    deck = Deck(
        deck_id="oracle-wins",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Heading"),
                    Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=0.0,
                        y=0.0,
                        width=100.0,
                        height=20.0,
                        font_size_pt=24.0,
                        font_family="Aptos",
                        revision=1,
                    ),
                    "n-2": ComputedNode(
                        x=0.0,
                        y=20.0,
                        width=100.0,
                        height=80.0,
                        font_size_pt=7.0,
                        font_family="Aptos",
                        revision=1,
                        text_overflow=True,
                    ),
                },
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )
    deck_path = suite_dir / "title_content" / "nominal" / "deck.json"
    _write_deck(deck_path, deck)
    _write_computed_sidecar(deck_path, deck)

    artifact_dir = run_dir / "brand-template" / "title_content" / "nominal" / "review"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "signals.json").write_text(
        json.dumps(
            [
                {
                    "slide_index": 0,
                    "layout_slug": "title_content",
                    "signals": {
                        "text_clipped": False,
                        "placeholder_empty": False,
                        "image_missing": False,
                        "font_too_small": False,
                    },
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_scores(run_dir / "brand-template" / "title_content" / "nominal" / "scores.json", build_success=1.0)

    exit_code = module.main(["--suite-dir", str(suite_dir), "--output", str(output_path)])

    assert exit_code == 0
    coverage = json.loads(output_path.read_text(encoding="utf-8"))
    assert coverage["coverage_pct"] == 100.0
    layout = coverage["layouts"][0]
    assert layout["status"] == "pass"
    assert layout["failure_reasons"] == []
    variant = layout["variants"][0]
    assert variant["overflow"] is False
    assert variant["font_too_small"] is False
    assert variant["pass"] is True
