from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_slides.cli import cli
from agent_slides.io import read_deck
from agent_slides.model import BuiltinLayoutProvider, ComputedNode, Counters, Deck, Node, Slide, resolve_layout_provider
from agent_slides.render_oracle import generate_render_signals
from tests.test_e2e_template import create_test_template


def test_generate_render_signals_flags_expected_builtin_conditions() -> None:
    deck = Deck(
        deck_id="deck-signals",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(node_id="n-1", slot_binding="heading", type="text", content="Signal title"),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=0.0,
                        y=0.0,
                        width=100.0,
                        height=40.0,
                        font_size_pt=7.5,
                        font_family="Aptos",
                        revision=1,
                        text_overflow=True,
                    )
                },
            ),
            Slide(
                slide_id="s-2",
                layout="image_left",
                nodes=[
                    Node(node_id="n-2", slot_binding="heading", type="text", content="Image slide"),
                    Node(node_id="n-3", slot_binding="body", type="text", content="Body copy"),
                ],
                computed={
                    "n-2": ComputedNode(
                        x=0.0,
                        y=0.0,
                        width=100.0,
                        height=30.0,
                        font_size_pt=24.0,
                        font_family="Aptos",
                        revision=1,
                    ),
                    "n-3": ComputedNode(
                        x=0.0,
                        y=40.0,
                        width=100.0,
                        height=60.0,
                        font_size_pt=14.0,
                        font_family="Aptos",
                        revision=1,
                    ),
                },
            ),
        ],
        counters=Counters(slides=2, nodes=3),
    )

    signals = generate_render_signals(deck, BuiltinLayoutProvider())

    assert signals == [
        {
            "slide_index": 0,
            "layout_slug": "title_content",
            "signals": {
                "text_clipped": True,
                "placeholder_empty": True,
                "image_missing": False,
                "font_too_small": True,
            },
        },
        {
            "slide_index": 1,
            "layout_slug": "image_left",
            "signals": {
                "text_clipped": False,
                "placeholder_empty": True,
                "image_missing": True,
                "font_too_small": False,
            },
        },
    ]


def test_generate_render_signals_supports_template_layouts(tmp_path: Path) -> None:
    template_path = tmp_path / "brand-template.pptx"
    deck_path = tmp_path / "deck.json"
    create_test_template(template_path)

    runner = CliRunner()
    learn_result = runner.invoke(cli, ["learn", str(template_path)])
    assert learn_result.exit_code == 0

    manifest_path = tmp_path / "brand-template.manifest.json"
    init_result = runner.invoke(cli, ["init", str(deck_path), "--template", str(manifest_path)])
    assert init_result.exit_code == 0

    add_result = runner.invoke(cli, ["slide", "add", str(deck_path), "--layout", "title_slide"])
    assert add_result.exit_code == 0

    slot_result = runner.invoke(
        cli,
        ["slot", "set", str(deck_path), "--slide", "0", "--slot", "heading", "--text", "Template title"],
    )
    assert slot_result.exit_code == 0

    deck = read_deck(str(deck_path))
    provider = resolve_layout_provider(str(manifest_path))
    signals = generate_render_signals(deck, provider)

    assert signals == [
        {
            "slide_index": 0,
            "layout_slug": "title_slide",
            "signals": {
                "text_clipped": False,
                "placeholder_empty": True,
                "image_missing": False,
                "font_too_small": False,
            },
        }
    ]


def test_review_command_writes_signals_json(monkeypatch, tmp_path: Path) -> None:
    from tests.test_review import fake_render_factory, write_deck

    deck_path = tmp_path / "deck.json"
    output_dir = tmp_path / "review-artifacts"
    write_deck(
        deck_path,
        Deck(
            deck_id="deck-review-signals",
            slides=[
                Slide(
                    slide_id="s-1",
                    layout="image_left",
                    nodes=[
                        Node(node_id="n-1", slot_binding="heading", type="text", content="Signal review"),
                        Node(node_id="n-2", slot_binding="body", type="text", content="Body"),
                    ],
                )
            ],
            counters=Counters(slides=1, nodes=2),
        ),
    )
    monkeypatch.setattr("agent_slides.review.render_pptx_to_pngs", fake_render_factory())

    runner = CliRunner()
    result = runner.invoke(cli, ["review", str(deck_path), "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    signals = json.loads((output_dir / "signals.json").read_text(encoding="utf-8"))
    assert signals == [
        {
            "slide_index": 0,
            "layout_slug": "image_left",
            "signals": {
                "text_clipped": False,
                "placeholder_empty": True,
                "image_missing": True,
                "font_too_small": False,
            },
        }
    ]
