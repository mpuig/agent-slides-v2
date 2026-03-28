from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from click.testing import CliRunner, Result

from agent_slides.cli import cli
from agent_slides.errors import (
    FILE_EXISTS,
    FILE_NOT_FOUND,
    INVALID_LAYOUT,
    INVALID_NODE,
    INVALID_SLIDE,
    INVALID_SLOT,
    SLOT_OCCUPIED,
    THEME_NOT_FOUND,
    UNBOUND_NODES,
)
from agent_slides.io import init_deck, read_deck
from agent_slides.model import Counters, Deck, Node, Slide, get_layout, list_layouts


def read_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def build_slide(slide_id: str, layout: str, slots: list[str], *, start_node: int = 1) -> Slide:
    return Slide(
        slide_id=slide_id,
        layout=layout,
        nodes=[
            Node(
                node_id=f"n-{start_node + offset}",
                slot_binding=slot_name,
                type="text",
                content=f"{slide_id}:{slot_name}",
            )
            for offset, slot_name in enumerate(slots)
        ],
    )


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


def invoke_cli(args: list[str]) -> Result:
    runner = CliRunner()
    return runner.invoke(cli, args)


def test_init_creates_valid_deck_file_and_reports_success_json(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = invoke_cli(["init", str(deck_path)])

    assert result.exit_code == 0
    response = json.loads(result.output)
    payload = read_payload(deck_path)

    assert response["ok"] is True
    assert response["data"] == {
        "deck_id": payload["deck_id"],
        "theme": "default",
        "design_rules": "default",
    }
    assert UUID(str(payload["deck_id"]))
    assert payload["revision"] == 0
    assert payload["slides"] == []
    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"
    assert payload["version"] == 1
    assert payload["_counters"] == {"slides": 0, "nodes": 0}


def test_init_applies_explicit_theme_and_rules_options(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = invoke_cli(["init", str(deck_path), "--theme", "default", "--rules", "default"])

    assert result.exit_code == 0
    payload = read_payload(deck_path)

    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"


def test_init_returns_file_exists_error_when_target_exists(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")

    result = invoke_cli(["init", str(deck_path)])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_EXISTS,
            "message": f"Deck file already exists: {deck_path}",
        },
    }


def test_init_force_overwrites_existing_file(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(
        json.dumps({"deck_id": "old", "revision": 9, "slides": ["stale"]}),
        encoding="utf-8",
    )

    result = invoke_cli(["init", str(deck_path), "--force"])

    assert result.exit_code == 0
    payload = read_payload(deck_path)

    assert payload["revision"] == 0
    assert payload["slides"] == []
    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"
    assert payload["deck_id"] != "old"


def test_init_returns_theme_validation_error_for_invalid_theme(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = invoke_cli(["init", str(deck_path), "--theme", "missing"])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": THEME_NOT_FOUND,
            "message": "Theme 'missing' was not found.",
        },
    }
    assert not deck_path.exists()


def test_init_returns_rules_validation_error_for_invalid_rules(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = invoke_cli(["init", str(deck_path), "--rules", "missing"])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_NOT_FOUND,
            "message": "Design rules profile 'missing' was not found.",
        },
    }
    assert not deck_path.exists()


def test_slide_add_creates_layout_bound_nodes(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)

    result = invoke_cli(["slide", "add", str(deck_path), "--layout", "title"])
    payload = json.loads(result.stdout)
    deck = read_deck(str(deck_path))
    layout = get_layout("title")

    assert result.exit_code == 0
    assert payload == {
        "ok": True,
        "data": {
            "slide_index": 0,
            "slide_id": "s-1",
            "layout": "title",
        },
    }
    assert [node.slot_binding for node in deck.slides[0].nodes] == list(layout.slots)
    assert [node.node_id for node in deck.slides[0].nodes] == ["n-1", "n-2"]


def test_slide_add_invalid_layout_returns_json_error_with_available_layouts(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)

    result = invoke_cli(["slide", "add", str(deck_path), "--layout", "nope"])
    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == INVALID_LAYOUT
    for layout_name in list_layouts():
        assert layout_name in payload["error"]["message"]


def test_slide_remove_by_index_shifts_remaining_slides(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = Deck(
        deck_id="deck-1",
        slides=[
            build_slide("s-1", "title", ["title", "subtitle"], start_node=1),
            build_slide("s-2", "title", ["title", "subtitle"], start_node=3),
        ],
        counters=Counters(slides=2, nodes=4),
    )
    write_deck(deck_path, deck)

    result = invoke_cli(["slide", "remove", str(deck_path), "--slide", "0"])
    payload = json.loads(result.stdout)
    updated = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert payload == {
        "ok": True,
        "data": {
            "removed": "s-1",
            "slide_count": 1,
        },
    }
    assert [slide.slide_id for slide in updated.slides] == ["s-2"]
    assert updated.get_slide(0).slide_id == "s-2"


def test_slide_remove_last_slide_leaves_empty_deck(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = Deck(
        deck_id="deck-1",
        slides=[build_slide("s-1", "title", ["title", "subtitle"], start_node=1)],
        counters=Counters(slides=1, nodes=2),
    )
    write_deck(deck_path, deck)

    result = invoke_cli(["slide", "remove", str(deck_path), "--slide", "0"])
    payload = json.loads(result.stdout)
    updated = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert payload["data"] == {"removed": "s-1", "slide_count": 0}
    assert updated.slides == []


def test_slide_remove_invalid_ref_returns_invalid_slide(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = Deck(deck_id="deck-1")
    write_deck(deck_path, deck)

    result = invoke_cli(["slide", "remove", str(deck_path), "--slide", "9"])
    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["error"]["code"] == INVALID_SLIDE


def test_slide_remove_accepts_slide_id_reference(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = Deck(
        deck_id="deck-1",
        slides=[
            build_slide("s-1", "title", ["title", "subtitle"], start_node=1),
            build_slide("s-2", "title", ["title", "subtitle"], start_node=3),
        ],
        counters=Counters(slides=2, nodes=4),
    )
    write_deck(deck_path, deck)

    result = invoke_cli(["slide", "remove", str(deck_path), "--slide", "s-1"])
    payload = json.loads(result.stdout)
    updated = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert payload["data"] == {"removed": "s-1", "slide_count": 1}
    assert [slide.slide_id for slide in updated.slides] == ["s-2"]


def test_slide_set_layout_rebinds_content_and_warns_on_unbound_nodes(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    slide = build_slide("s-1", "three_col", ["title", "col1", "col2", "col3"], start_node=1)
    deck = Deck(
        deck_id="deck-1",
        slides=[slide],
        counters=Counters(slides=1, nodes=4),
    )
    write_deck(deck_path, deck)

    result = invoke_cli(
        ["slide", "set-layout", str(deck_path), "--slide", "s-1", "--layout", "two_col"]
    )
    payload = json.loads(result.stdout)
    warning = json.loads(result.stderr)
    updated = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert payload == {
        "ok": True,
        "data": {
            "slide_id": "s-1",
            "layout": "two_col",
            "unbound_nodes": ["n-4"],
        },
    }
    assert warning == {
        "ok": True,
        "warning": {
            "code": UNBOUND_NODES,
            "message": "1 node(s) became unbound during slot rebinding.",
        },
        "data": {
            "slide_id": "s-1",
            "unbound_nodes": ["n-4"],
        },
    }
    assert updated.slides[0].layout == "two_col"
    assert [node.slot_binding for node in updated.slides[0].nodes] == [
        "title",
        "col1",
        "col2",
        None,
    ]


def test_slide_set_layout_to_same_layout_has_no_unbound_nodes(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    slide = build_slide("s-1", "two_col", ["title", "col1", "col2"], start_node=1)
    deck = Deck(
        deck_id="deck-1",
        slides=[slide],
        counters=Counters(slides=1, nodes=3),
    )
    write_deck(deck_path, deck)

    result = invoke_cli(
        ["slide", "set-layout", str(deck_path), "--slide", "0", "--layout", "two_col"]
    )
    payload = json.loads(result.stdout)
    updated = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert result.stderr == ""
    assert payload == {
        "ok": True,
        "data": {
            "slide_id": "s-1",
            "layout": "two_col",
            "unbound_nodes": [],
        },
    }
    assert [node.slot_binding for node in updated.slides[0].nodes] == list(get_layout("two_col").slots)
    assert len(updated.slides[0].nodes) == 3


def test_slide_set_layout_invalid_slide_returns_invalid_slide(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)

    result = invoke_cli(
        ["slide", "set-layout", str(deck_path), "--slide", "s-999", "--layout", "title"]
    )
    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["error"]["code"] == INVALID_SLIDE


def test_slide_set_layout_invalid_layout_returns_invalid_layout(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)

    result = invoke_cli(["slide", "set-layout", str(deck_path), "--slide", "0", "--layout", "bad"])
    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["error"]["code"] == INVALID_LAYOUT


def test_slot_set_sets_text_content_by_index(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
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
        ["slot", "set", str(deck_path), "--slide", "0", "--slot", "title", "--text", "Quarterly update"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"slide_id": "s-1", "slot": "title", "text": "Quarterly update"},
    }
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == "Quarterly update"


def test_slot_set_overwrites_existing_content_by_slide_id(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
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
        ["slot", "set", str(deck_path), "--slide", "s-1", "--slot", "title", "--text", "New content"]
    )

    deck = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert deck.slides[0].nodes[0].content == "New content"


def test_slot_set_creates_node_and_stores_font_size_override(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        build_deck(
            Slide(slide_id="s-1", layout="title", nodes=[]),
            node_count=0,
        ),
    )

    result = invoke_cli(
        [
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
        ]
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
    write_deck(deck_path, build_deck(Slide(slide_id="s-1", layout="title", nodes=[]), node_count=0))

    result = invoke_cli(
        ["slot", "set", str(deck_path), "--slide", "s-9", "--slot", "title", "--text", "Missing slide"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == INVALID_SLIDE


def test_slot_set_invalid_slot_lists_valid_slots(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, build_deck(Slide(slide_id="s-1", layout="title", nodes=[]), node_count=0))

    result = invoke_cli(
        ["slot", "set", str(deck_path), "--slide", "s-1", "--slot", "bogus", "--text", "Nope"]
    )

    payload = json.loads(result.stderr)

    assert result.exit_code == 1
    assert payload["error"]["code"] == INVALID_SLOT
    assert "title" in payload["error"]["message"]
    assert "subtitle" in payload["error"]["message"]


def test_slot_clear_clears_content_to_empty_string(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="Clear me")],
            )
        ),
    )

    result = invoke_cli(["slot", "clear", str(deck_path), "--slide", "s-1", "--slot", "title"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"slide_id": "s-1", "slot": "title", "cleared": True},
    }
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == ""


def test_slot_clear_on_already_empty_slot_is_success(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[Node(node_id="n-1", slot_binding="title", type="text", content="")],
            )
        ),
    )

    result = invoke_cli(["slot", "clear", str(deck_path), "--slide", "s-1", "--slot", "title"])

    assert result.exit_code == 0
    assert read_deck(str(deck_path)).slides[0].nodes[0].content == ""


def test_slot_bind_rebinds_unbound_node_to_slot(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        build_deck(
            Slide(
                slide_id="s-1",
                layout="two_col",
                nodes=[Node(node_id="n-1", slot_binding=None, type="text", content="Body")],
            )
        ),
    )

    result = invoke_cli(["slot", "bind", str(deck_path), "--node", "n-1", "--slot", "col2"])

    deck = read_deck(str(deck_path))

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "data": {"node_id": "n-1", "slot": "col2", "bound": True},
    }
    assert deck.slides[0].nodes[0].slot_binding == "col2"


def test_slot_bind_to_occupied_slot_returns_slot_occupied_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
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

    result = invoke_cli(["slot", "bind", str(deck_path), "--node", "n-2", "--slot", "col2"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == SLOT_OCCUPIED


def test_slot_bind_invalid_node_id_returns_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(
        deck_path,
        build_deck(Slide(slide_id="s-1", layout="two_col", nodes=[]), node_count=0),
    )

    result = invoke_cli(["slot", "bind", str(deck_path), "--node", "n-404", "--slot", "col2"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == INVALID_NODE
