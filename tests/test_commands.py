from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from click.testing import CliRunner, Result
from pptx import Presentation

from agent_slides.cli import cli
from agent_slides.errors import (
    FILE_EXISTS,
    FILE_NOT_FOUND,
    INVALID_LAYOUT,
    INVALID_SLIDE,
    INVALID_SLOT,
    SCHEMA_ERROR,
    THEME_NOT_FOUND,
    UNBOUND_NODES,
)
from agent_slides.io import init_deck, read_deck
from agent_slides.model import Counters, Deck, Node, Slide, get_layout, list_layouts
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.types import ComputedNode


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


def make_empty_deck() -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=0,
        theme="default",
        design_rules="default",
        slides=[],
        counters=Counters(),
    )


def invoke_cli(args: list[str], *, input: str | None = None) -> Result:
    runner = CliRunner()
    return runner.invoke(cli, args, input=input)


def make_computed_node(font_size_pt: float, *, overflow: bool = False) -> ComputedNode:
    return ComputedNode(
        x=72.0,
        y=54.0,
        width=576.0,
        height=80.0,
        font_size_pt=font_size_pt,
        font_family="Aptos",
        color="#333333",
        bg_color="#FFFFFF",
        font_bold=False,
        text_overflow=overflow,
        revision=1,
    )


def make_clean_deck() -> Deck:
    return Deck(
        deck_id="deck-clean",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Deck title",
                    )
                ],
                computed={"n-1": make_computed_node(28.0)},
            ),
            Slide(
                slide_id="s-2",
                layout="closing",
                nodes=[
                    Node(
                        node_id="n-2",
                        slot_binding="body",
                        type="text",
                        content="Thanks",
                    )
                ],
                computed={"n-2": make_computed_node(14.0)},
            ),
        ],
    )


def make_overflow_deck() -> Deck:
    rules = load_design_rules("default")
    return Deck(
        deck_id="deck-overflow",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Overflow heading",
                    )
                ],
                computed={
                    "n-1": make_computed_node(
                        float(rules.overflow_policy.min_font_size),
                        overflow=True,
                    )
                },
            ),
            Slide(
                slide_id="s-2",
                layout="closing",
                nodes=[
                    Node(
                        node_id="n-2",
                        slot_binding="body",
                        type="text",
                        content="Bye",
                    )
                ],
                computed={"n-2": make_computed_node(14.0)},
            ),
        ],
    )


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
            build_slide("s-1", "title", ["heading", "subheading"], start_node=1),
            build_slide("s-2", "title", ["heading", "subheading"], start_node=3),
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
        slides=[build_slide("s-1", "title", ["heading", "subheading"], start_node=1)],
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
            build_slide("s-1", "title", ["heading", "subheading"], start_node=1),
            build_slide("s-2", "title", ["heading", "subheading"], start_node=3),
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
    slide = build_slide("s-1", "three_col", ["heading", "col1", "col2", "col3"], start_node=1)
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
        "heading",
        "col1",
        "col2",
        None,
    ]


def test_slide_set_layout_to_same_layout_has_no_unbound_nodes(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    slide = build_slide("s-1", "two_col", ["heading", "col1", "col2"], start_node=1)
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

def test_batch_applies_multiple_operations_atomically(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())

    result = invoke_cli(
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
    assert payload["data"]["results"][0] == {
        "slide_index": 0,
        "slide_id": "s-1",
        "layout": "title",
    }

    deck = read_deck(str(deck_path))
    assert deck.revision == 1
    assert [slide.layout for slide in deck.slides] == ["title", "two_col"]
    assert [(node.slot_binding, node.content) for node in deck.slides[0].nodes] == [
        ("heading", "Hello"),
        ("subheading", "World"),
    ]
    assert deck.slides[0].nodes[1].style_overrides["font_size"] == 18.0
    assert [(node.slot_binding, node.content) for node in deck.slides[1].nodes] == [
        ("heading", "Key Points"),
        ("col1", ""),
        ("col2", ""),
    ]


def test_batch_rolls_back_and_reports_operation_index_on_failure(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())
    original_payload = deck_path.read_text(encoding="utf-8")

    result = invoke_cli(
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

    result = invoke_cli(["batch", str(deck_path)], input="[]")

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "ok": True,
        "data": {"operations": 0, "results": []},
    }
    assert read_deck(str(deck_path)).revision == 0


def test_batch_invalid_json_returns_schema_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_empty_deck())

    result = invoke_cli(["batch", str(deck_path)], input="{not json")

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

    result = invoke_cli(
        ["batch", str(deck_path)],
        input=json.dumps(
            [
                {"command": "slot_bind", "args": {"node": "n-1", "slot": "title"}},
                {"command": "slot_set", "args": {"slide": "s-1", "slot": "subtitle", "text": "Intro"}},
                {"command": "slide_add", "args": {"layout": "two_col"}},
                {"command": "slot_set", "args": {"slide": 1, "slot": "left", "text": "Key Points"}},
                {"command": "slot_clear", "args": {"slide": 1, "slot": "left"}},
                {"command": "slide_set_layout", "args": {"slide": 1, "layout": "three_col"}},
                {"command": "slide_remove", "args": {"slide": 1}},
            ]
        ),
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data"]["operations"] == 7
    assert payload["data"]["results"][0] == {
        "slide_id": "s-1",
        "slot": "heading",
        "node_id": "n-1",
    }
    assert payload["data"]["results"][5] == {
        "slide_id": "s-2",
        "layout": "three_col",
        "unbound_nodes": [],
    }
    assert payload["data"]["results"][6] == {
        "removed": "s-2",
        "slide_count": 1,
    }

    deck = read_deck(str(deck_path))
    assert len(deck.slides) == 1
    assert deck.slides[0].nodes[0].node_id == "n-1"
    assert deck.slides[0].nodes[0].slot_binding == "heading"
    assert deck.slides[0].nodes[0].content == "Loose title"
    assert deck.slides[0].nodes[1].slot_binding == "subheading"
    assert deck.slides[0].nodes[1].content == "Intro"


def test_batch_uses_single_mutate_deck_call(monkeypatch) -> None:
    calls: list[str] = []

    def fake_mutate_deck(path: str, fn):
        calls.append(path)
        results = fn(Deck(deck_id="deck-1"))
        return Deck(deck_id="deck-1"), results

    monkeypatch.setattr("agent_slides.commands.batch.mutate_deck", fake_mutate_deck)

    result = invoke_cli(
        ["batch", "deck.json"],
        input=json.dumps([{"command": "slide_add", "args": {"layout": "title"}}]),
    )

    assert result.exit_code == 0
    assert calls == ["deck.json"]
    assert json.loads(result.output)["data"]["operations"] == 1


def test_build_command_creates_valid_pptx_and_reports_slide_count(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    output_path = tmp_path / "presentation.pptx"
    write_deck(deck_path, make_clean_deck())

    result = invoke_cli(["build", str(deck_path), "-o", str(output_path)])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert json.loads(result.output) == {
        "ok": True,
        "data": {
            "output": str(output_path),
            "slides": 2,
        },
    }
    presentation = Presentation(output_path)
    assert len(presentation.slides) == 2


def test_build_command_reports_missing_deck_as_file_not_found(tmp_path: Path) -> None:
    result = invoke_cli(
        ["build", str(tmp_path / "missing.json"), "-o", str(tmp_path / "presentation.pptx")]
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_NOT_FOUND,
            "message": f"Deck file not found: {tmp_path / 'missing.json'}",
        },
    }


def test_validate_command_reports_clean_deck(tmp_path: Path) -> None:
    deck_path = tmp_path / "clean.json"
    write_deck(deck_path, make_clean_deck())

    result = invoke_cli(["validate", str(deck_path)])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert json.loads(result.output) == {
        "ok": True,
        "data": {
            "warnings": [],
            "clean": True,
        },
    }


def test_validate_command_returns_structured_overflow_warning(tmp_path: Path) -> None:
    deck_path = tmp_path / "overflow.json"
    write_deck(deck_path, make_overflow_deck())

    result = invoke_cli(["validate", str(deck_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["clean"] is False
    assert any(warning["code"] == "OVERFLOW" for warning in payload["data"]["warnings"])
    for warning in payload["data"]["warnings"]:
        assert {"code", "severity", "message"} <= warning.keys()


def test_info_command_dumps_indented_deck_json(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = make_clean_deck()
    write_deck(deck_path, deck)

    result = invoke_cli(["info", str(deck_path)])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.output == f"{deck.model_dump_json(by_alias=True, indent=2)}\n"
    assert result.output.startswith("{\n  ")


def test_info_command_reports_missing_deck_as_file_not_found(tmp_path: Path) -> None:
    result = invoke_cli(["info", str(tmp_path / "missing.json")])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_NOT_FOUND,
            "message": f"Deck file not found: {tmp_path / 'missing.json'}",
        },
    }
