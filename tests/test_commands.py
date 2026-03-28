from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_slides.cli import cli
from agent_slides.errors import INVALID_NODE, INVALID_SLIDE, INVALID_SLOT, SLOT_OCCUPIED
from agent_slides.io.sidecar import read_deck
from agent_slides.model import Counters, Deck, Node, Slide


def build_deck(*slides: Slide, revision: int = 2, node_count: int | None = None) -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=revision,
        slides=list(slides),
        counters=Counters(
            slides=len(slides),
            nodes=node_count if node_count is not None else sum(len(slide.nodes) for slide in slides),
        ),
    )


def write_raw_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def invoke_cli(*args: str):
    runner = CliRunner()
    return runner.invoke(cli, list(args))

def test_slot_set_sets_text_content_by_index(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="Old title")],
            )
        ),
    )

    result = invoke_cli(
        "slot",
        "set",
        str(deck_path),
        "--slide",
        "0",
        "--slot",
        "title",
        "--text",
        "Quarterly update",
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"slide_id": "s-1", "slot": "title", "text": "Quarterly update"},
    }
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == "Quarterly update"


def test_slot_set_overwrites_existing_content_by_slide_id(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="Old content")],
            )
        ),
    )

    result = invoke_cli(
        "slot",
        "set",
        str(deck_path),
        "--slide",
        "s-1",
        "--slot",
        "title",
        "--text",
        "New content",
    )

    deck = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert deck.slides[0].nodes[0].content == "New content"


def test_slot_set_creates_node_and_stores_font_size_override(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(slide_id="s-1", layout="title", nodes=[]),
            node_count=0,
        ),
    )

    result = invoke_cli(
        "slot",
        "set",
        str(deck_path),
        "--slide",
        "s-1",
        "--slot",
        "title",
        "--text",
        "Created title",
        "--font-size",
        "30",
    )

    deck = read_deck(str(deck_path))
    created = deck.slides[0].nodes[0]

    assert result.exit_code == 0
    assert created.node_id == "n-1"
    assert created.slot_binding == "title"
    assert created.content == "Created title"
    assert created.style_overrides["font_size_pt"] == 30.0
    assert created.style_overrides["text_fit_disabled"] is True


def test_slot_set_invalid_slide_returns_invalid_slide_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(Slide(slide_id="s-1", layout="title", nodes=[]), node_count=0))

    result = invoke_cli(
        "slot",
        "set",
        str(deck_path),
        "--slide",
        "s-9",
        "--slot",
        "title",
        "--text",
        "Missing slide",
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == INVALID_SLIDE


def test_slot_set_invalid_slot_lists_valid_slots(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(Slide(slide_id="s-1", layout="title", nodes=[]), node_count=0))

    result = invoke_cli(
        "slot",
        "set",
        str(deck_path),
        "--slide",
        "s-1",
        "--slot",
        "bogus",
        "--text",
        "Nope",
    )

    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["error"]["code"] == INVALID_SLOT
    assert "title" in payload["error"]["message"]
    assert "subtitle" in payload["error"]["message"]


def test_slot_clear_clears_content_to_empty_string(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="Clear me")],
            )
        ),
    )

    result = invoke_cli("slot", "clear", str(deck_path), "--slide", "s-1", "--slot", "title")

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"slide_id": "s-1", "slot": "title", "cleared": True},
    }
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == ""


def test_slot_clear_on_already_empty_slot_is_success(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="")],
            )
        ),
    )

    result = invoke_cli("slot", "clear", str(deck_path), "--slide", "s-1", "--slot", "title")

    assert result.exit_code == 0
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == ""


def test_slot_bind_rebinds_unbound_node_to_slot(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="two_col",
                nodes=[Node(node_id="n-1", slot_binding=None, type="text", content="Body")],
            )
        ),
    )

    result = invoke_cli("slot", "bind", str(deck_path), "--node", "n-1", "--slot", "col2")

    deck = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"node_id": "n-1", "slot": "col2", "bound": True},
    }
    assert deck.slides[0].nodes[0].slot_binding == "col2"


def test_slot_bind_to_occupied_slot_returns_slot_occupied_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="two_col",
                nodes=[
                    Node(node_id="n-1", slot_binding="col2", type="text", content="Taken"),
                    Node(node_id="n-2", slot_binding=None, type="text", content="Candidate"),
                ],
            )
        ),
    )

    result = invoke_cli("slot", "bind", str(deck_path), "--node", "n-2", "--slot", "col2")

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == SLOT_OCCUPIED


def test_slot_bind_invalid_node_id_returns_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        build_deck(Slide(slide_id="s-1", layout="two_col", nodes=[]), node_count=0),
    )

    result = invoke_cli("slot", "bind", str(deck_path), "--node", "n-404", "--slot", "col2")

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == INVALID_NODE
