from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_slides.cli import cli
from agent_slides.errors import INVALID_SLOT, SCHEMA_ERROR
from agent_slides.io.sidecar import read_deck
from agent_slides.model import Counters, Deck, Node, Slide


def write_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def make_empty_deck() -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=0,
        theme="default",
        design_rules="default",
        slides=[],
        counters=Counters(),
    )


def test_batch_applies_multiple_operations_atomically(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["batch", str(deck_path)],
        input=json.dumps(
            [
                {"command": "slide_add", "args": {"layout": "title"}},
                {"command": "slot_set", "args": {"slide": 0, "slot": "title", "text": "Hello"}},
                {
                    "command": "slot_set",
                    "args": {"slide": 0, "slot": "subtitle", "text": "World", "font_size": 18},
                },
                {"command": "slide_add", "args": {"layout": "two_col"}},
                {"command": "slot_set", "args": {"slide": 1, "slot": "title", "text": "Key Points"}},
            ]
        ),
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["operations"] == 5
    assert [item["command"] for item in payload["data"]["results"]] == [
        "slide_add",
        "slot_set",
        "slot_set",
        "slide_add",
        "slot_set",
    ]

    deck = read_deck(str(deck_path))
    assert deck.revision == 1
    assert [slide.layout for slide in deck.slides] == ["title", "two_col"]
    assert [(node.slot_binding, node.content) for node in deck.slides[0].nodes] == [
        ("title", "Hello"),
        ("subtitle", "World"),
    ]
    assert deck.slides[0].nodes[1].style_overrides["font_size"] == 18.0
    assert [(node.slot_binding, node.content) for node in deck.slides[1].nodes] == [
        ("title", "Key Points")
    ]


def test_batch_rolls_back_and_reports_operation_index_on_failure(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())
    original_payload = deck_path.read_text(encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["batch", str(deck_path)],
        input=json.dumps(
            [
                {"command": "slide_add", "args": {"layout": "title"}},
                {"command": "slot_set", "args": {"slide": 0, "slot": "body", "text": "Nope"}},
            ]
        ),
    )

    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert error["code"] == INVALID_SLOT
    assert error["operation_index"] == 1
    assert deck_path.read_text(encoding="utf-8") == original_payload
    assert read_deck(str(deck_path)).slides == []


def test_batch_empty_array_is_a_successful_no_op(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())

    runner = CliRunner()
    result = runner.invoke(cli, ["batch", str(deck_path)], input="[]")

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "ok": True,
        "data": {"operations": 0, "results": []},
    }
    assert read_deck(str(deck_path)).revision == 0


def test_batch_invalid_json_returns_schema_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())

    runner = CliRunner()
    result = runner.invoke(cli, ["batch", str(deck_path)], input="{not json")

    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert error["code"] == SCHEMA_ERROR
    assert "Invalid JSON batch payload" in error["message"]


def test_batch_supports_all_mutation_types(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        Deck(
            deck_id="deck-1",
            revision=0,
            theme="default",
            design_rules="default",
            slides=[
                Slide(
                    slide_id="s-1",
                    layout="title",
                    nodes=[Node(node_id="n-1", slot_binding=None, type="text", content="Loose title")],
                )
            ],
            counters=Counters(slides=1, nodes=1),
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["batch", str(deck_path)],
        input=json.dumps(
            [
                {"command": "slot_bind", "args": {"node": "n-1", "slot": "title"}},
                {"command": "slot_set", "args": {"slide": "s-1", "slot": "subtitle", "text": "Intro"}},
                {"command": "slide_add", "args": {"layout": "two_col"}},
                {"command": "slot_set", "args": {"slide": 1, "slot": "title", "text": "Key Points"}},
                {"command": "slot_clear", "args": {"slide": 1, "slot": "title"}},
                {"command": "slide_set_layout", "args": {"slide": 1, "layout": "closing"}},
                {"command": "slide_remove", "args": {"slide": 1}},
            ]
        ),
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data"]["operations"] == 7
    assert {item["command"] for item in payload["data"]["results"]} == {
        "slot_bind",
        "slot_set",
        "slide_add",
        "slot_clear",
        "slide_set_layout",
        "slide_remove",
    }

    deck = read_deck(str(deck_path))
    assert len(deck.slides) == 1
    assert deck.slides[0].nodes[0].node_id == "n-1"
    assert deck.slides[0].nodes[0].slot_binding == "title"
    assert deck.slides[0].nodes[0].content == "Loose title"
    assert deck.slides[0].nodes[1].slot_binding == "subtitle"
    assert deck.slides[0].nodes[1].content == "Intro"


def test_batch_uses_single_mutate_deck_call(monkeypatch) -> None:
    calls: list[str] = []

    def fake_mutate_deck(path: str, fn):
        calls.append(path)
        results = fn(Deck(deck_id="deck-1"))
        return Deck(deck_id="deck-1"), results

    monkeypatch.setattr("agent_slides.commands.batch.mutate_deck", fake_mutate_deck)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["batch", "deck.json"],
        input=json.dumps([{"command": "slide_add", "args": {"layout": "title"}}]),
    )

    assert result.exit_code == 0
    assert calls == ["deck.json"]
    assert json.loads(result.output)["data"]["operations"] == 1

