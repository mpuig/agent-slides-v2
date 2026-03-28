from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from pptx import Presentation

from agent_slides.cli import cli
from agent_slides.errors import UNBOUND_NODES


def collect_slide_text(path: Path) -> list[str]:
    presentation = Presentation(str(path))
    text_values: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                text_values.append(shape.text_frame.text)
    return text_values


def invoke(runner: CliRunner, args: list[str], *, input_text: str | None = None) -> tuple[int, dict[str, object], str]:
    result = runner.invoke(cli, args, input=input_text)
    payload = json.loads(result.stdout) if result.stdout else {}
    return result.exit_code, payload, result.stderr


def test_full_demo_flow(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"
    pptx_path = tmp_path / "output.pptx"

    exit_code, payload, _ = invoke(runner, ["init", str(deck_path), "--theme", "default"])
    assert exit_code == 0
    assert payload["ok"] is True

    for layout in ["title", "two_col", "quote"]:
        exit_code, payload, _ = invoke(runner, ["slide", "add", str(deck_path), "--layout", layout])
        assert exit_code == 0
        assert payload["ok"] is True

    slot_sets = [
        ("0", "title", "My Presentation"),
        ("0", "subtitle", "March 2026"),
        ("1", "title", "Key Points"),
        ("1", "col1", "First point"),
        ("1", "col2", "Second point"),
        ("2", "quote", "The best way to predict the future is to invent it."),
        ("2", "attribution", "Alan Kay"),
        ("1", "title", "Three Key Points"),
    ]
    for slide_ref, slot_name, text in slot_sets:
        exit_code, payload, _ = invoke(
            runner,
            [
                "slot",
                "set",
                str(deck_path),
                "--slide",
                slide_ref,
                "--slot",
                slot_name,
                "--text",
                text,
            ],
        )
        assert exit_code == 0
        assert payload["ok"] is True

    exit_code, payload, _ = invoke(runner, ["build", str(deck_path), "-o", str(pptx_path)])
    assert exit_code == 0
    assert payload["ok"] is True

    presentation = Presentation(str(pptx_path))
    assert len(presentation.slides) == 3

    all_text = collect_slide_text(pptx_path)
    assert "My Presentation" in all_text
    assert "March 2026" in all_text
    assert "Three Key Points" in all_text
    assert "First point" in all_text
    assert "Second point" in all_text
    assert "The best way to predict the future is to invent it." in all_text
    assert "Alan Kay" in all_text


def test_layout_switch_content_migration(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"

    exit_code, payload, _ = invoke(runner, ["init", str(deck_path)])
    assert exit_code == 0
    assert payload["ok"] is True

    exit_code, payload, _ = invoke(runner, ["slide", "add", str(deck_path), "--layout", "three_col"])
    assert exit_code == 0
    assert payload["ok"] is True

    for slot_name, text in [("col1", "Column 1"), ("col2", "Column 2"), ("col3", "Column 3")]:
        exit_code, payload, _ = invoke(
            runner,
            [
                "slot",
                "set",
                str(deck_path),
                "--slide",
                "0",
                "--slot",
                slot_name,
                "--text",
                text,
            ],
        )
        assert exit_code == 0
        assert payload["ok"] is True

    result = runner.invoke(
        cli,
        ["slide", "set-layout", str(deck_path), "--slide", "0", "--layout", "two_col"],
    )
    output = json.loads(result.stdout)
    warning = json.loads(result.stderr)

    assert result.exit_code == 0
    assert output["ok"] is True
    assert warning["warning"]["code"] == UNBOUND_NODES

    info_result = runner.invoke(cli, ["info", str(deck_path)])
    deck_data = json.loads(info_result.output)

    slide = deck_data["slides"][0]
    assert slide["layout"] == "two_col"

    bound_slots = {node["slot_binding"] for node in slide["nodes"] if node["slot_binding"]}
    assert "col1" in bound_slots
    assert "col2" in bound_slots

    unbound = [node for node in slide["nodes"] if node["slot_binding"] is None]
    assert len(unbound) >= 1
    assert any(
        node["content"]["blocks"] == [{"type": "paragraph", "text": "Column 3", "level": 0}]
        for node in unbound
    )


def test_batch_creates_full_deck(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"
    pptx_path = tmp_path / "batch.pptx"

    exit_code, payload, _ = invoke(runner, ["init", str(deck_path)])
    assert exit_code == 0
    assert payload["ok"] is True

    batch_input = json.dumps(
        [
            {"command": "slide_add", "args": {"layout": "title"}},
            {"command": "slot_set", "args": {"slide": 0, "slot": "title", "text": "Batch Created"}},
            {"command": "slide_add", "args": {"layout": "quote"}},
            {
                "command": "slot_set",
                "args": {"slide": 1, "slot": "quote", "text": "Efficiency is doing things right."},
            },
        ]
    )

    exit_code, payload, _ = invoke(runner, ["batch", str(deck_path)], input_text=batch_input)
    assert exit_code == 0
    assert payload["ok"] is True

    exit_code, payload, _ = invoke(runner, ["build", str(deck_path), "-o", str(pptx_path)])
    assert exit_code == 0
    assert payload["ok"] is True

    presentation = Presentation(str(pptx_path))
    assert len(presentation.slides) == 2
