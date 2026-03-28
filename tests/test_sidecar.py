from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

import agent_slides.io.sidecar as sidecar
from agent_slides.errors import (
    AgentSlidesError,
    FILE_EXISTS,
    FILE_NOT_FOUND,
    REVISION_CONFLICT,
    SCHEMA_ERROR,
)
from agent_slides.io.sidecar import (
    computed_sidecar_path,
    init_deck,
    mutate_deck,
    read_computed_deck,
    read_deck,
    resolve_manifest_path,
    write_computed_deck,
    write_deck,
)
from agent_slides.model import BuiltinLayoutProvider, ComputedDeck, ComputedNode, Counters, Deck, Node, Slide


def build_deck(*, revision: int = 2, template_manifest: str | None = None) -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=revision,
        theme="classic",
        design_rules="strict",
        template_manifest=template_manifest,
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Hello world",
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=54.0,
                        width=576.0,
                        height=80.0,
                        font_size_pt=28.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color="#FFFFFF",
                        font_bold=True,
                        revision=revision,
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def write_raw_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def test_read_deck_loads_valid_json(tmp_path: Path) -> None:
    deck = build_deck()
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, deck)

    loaded = read_deck(str(deck_path))

    assert loaded == deck


def test_read_deck_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(AgentSlidesError) as exc_info:
        read_deck(str(tmp_path / "missing.json"))

    assert exc_info.value.code == FILE_NOT_FOUND


def test_read_deck_invalid_json_raises_schema_error(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(AgentSlidesError) as exc_info:
        read_deck(str(deck_path))

    assert exc_info.value.code == SCHEMA_ERROR
    assert "Invalid JSON" in exc_info.value.message


def test_read_deck_wrong_structure_raises_schema_error_with_details(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps({"deck_id": "deck-1", "slides": "nope"}), encoding="utf-8")

    with pytest.raises(AgentSlidesError) as exc_info:
        read_deck(str(deck_path))

    assert exc_info.value.code == SCHEMA_ERROR
    assert "slides" in exc_info.value.message


def test_read_deck_upgrades_legacy_string_content_and_version_one(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(
        json.dumps(
            {
                "version": 1,
                "deck_id": "deck-1",
                "revision": 0,
                "theme": "default",
                "design_rules": "default",
                "slides": [
                    {
                        "slide_id": "s-1",
                        "layout": "title",
                        "nodes": [
                            {
                                "node_id": "n-1",
                                "slot_binding": "heading",
                                "type": "text",
                                "content": "Legacy title",
                            }
                        ],
                    }
                ],
                "_counters": {"slides": 1, "nodes": 1},
            }
        ),
        encoding="utf-8",
    )

    deck = read_deck(str(deck_path))

    assert deck.version == 2
    assert deck.template_manifest is None
    assert deck.slides[0].nodes[0].content.model_dump(mode="json") == {
        "blocks": [{"type": "paragraph", "text": "Legacy title", "level": 0}]
    }


def test_read_deck_loads_v2_template_manifest(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(template_manifest="templates/demo/manifest.json"))

    deck = read_deck(str(deck_path))

    assert deck.version == 2
    assert deck.template_manifest == "templates/demo/manifest.json"


def test_write_deck_uses_atomic_temp_file_and_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck_path = tmp_path / "deck.json"
    computed_path = computed_sidecar_path(deck_path)
    deck = build_deck()
    write_raw_deck(deck_path, deck)

    renamed_paths: list[tuple[str, str]] = []
    original_rename = sidecar.os.rename

    def fake_rename(src: str | Path, dst: str | Path) -> None:
        renamed_paths.append((str(src), str(dst)))
        original_rename(src, dst)

    monkeypatch.setattr(sidecar.os, "rename", fake_rename)

    updated = build_deck(revision=3)
    write_deck(str(deck_path), updated, expected_revision=2)

    assert renamed_paths == [
        (f"{deck_path}.tmp", str(deck_path)),
        (f"{computed_path}.tmp", str(computed_path)),
    ]
    assert read_deck(str(deck_path)).revision == 3


def test_write_deck_revision_conflict_raises(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(revision=4))

    with pytest.raises(AgentSlidesError) as exc_info:
        write_deck(str(deck_path), build_deck(revision=5), expected_revision=3)

    assert exc_info.value.code == REVISION_CONFLICT


def test_write_deck_surfaces_os_errors_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck())

    def fake_rename(src: str | Path, dst: str | Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(sidecar.os, "rename", fake_rename)

    with pytest.raises(AgentSlidesError) as exc_info:
        write_deck(str(deck_path), build_deck(revision=3), expected_revision=2)

    assert exc_info.value.code == SCHEMA_ERROR
    assert "Failed to write deck file" in exc_info.value.message
    assert "disk full" in exc_info.value.message


def test_mutate_deck_runs_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(revision=2))

    reflow_revisions: list[int] = []
    provider_types: list[type[object]] = []

    def fake_reflow(deck: Deck, provider) -> None:
        reflow_revisions.append(deck.revision)
        provider_types.append(type(provider))

    monkeypatch.setattr("agent_slides.engine.reflow.reflow_deck", fake_reflow)

    def mutate(deck: Deck, provider) -> str:
        deck.theme = "updated"
        assert isinstance(provider, BuiltinLayoutProvider)
        return "ok"

    updated_deck, result = mutate_deck(str(deck_path), mutate)

    assert result == "ok"
    assert updated_deck.revision == 3
    assert updated_deck.theme == "updated"
    assert reflow_revisions == [3]
    assert provider_types == [BuiltinLayoutProvider]
    assert read_deck(str(deck_path)).theme == "updated"
    assert computed_sidecar_path(deck_path).exists()


def test_mutate_deck_does_not_write_if_mutation_raises(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    original = build_deck(revision=2)
    write_raw_deck(deck_path, original)
    original_payload = deck_path.read_text(encoding="utf-8")

    def fail(_: Deck, __) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        mutate_deck(str(deck_path), fail)

    assert deck_path.read_text(encoding="utf-8") == original_payload
    assert read_deck(str(deck_path)) == original


def test_init_deck_creates_new_file_with_defaults(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    computed_path = computed_sidecar_path(deck_path)

    deck = init_deck(str(deck_path), theme="modern", design_rules="default", force=False)

    assert deck_path.exists()
    assert computed_path.exists()
    assert deck.revision == 0
    assert deck.theme == "modern"
    assert deck.design_rules == "default"
    assert deck.slides == []
    assert deck.counters == Counters()
    assert UUID(deck.deck_id)
    assert read_computed_deck(str(deck_path)) == ComputedDeck(deck_id=deck.deck_id)


def test_init_deck_existing_file_without_force_raises(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck())

    with pytest.raises(AgentSlidesError) as exc_info:
        init_deck(str(deck_path), theme="modern", design_rules="default", force=False)

    assert exc_info.value.code == FILE_EXISTS


def test_init_deck_force_overwrites_existing_file(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck())

    deck = init_deck(str(deck_path), theme="new-theme", design_rules="new-rules", force=True)
    loaded = read_deck(str(deck_path))

    assert deck.theme == "new-theme"
    assert loaded.design_rules == "new-rules"
    assert loaded.revision == 0
    assert loaded.slides == []
    assert computed_sidecar_path(deck_path).exists()


def test_sidecar_round_trip_preserves_all_fields_and_counters_alias(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    original = build_deck(revision=7, template_manifest="templates/demo/manifest.json")
    write_raw_deck(deck_path, original)

    updated = read_deck(str(deck_path))
    write_deck(str(deck_path), updated, expected_revision=7)

    restored = read_deck(str(deck_path))
    payload = json.loads(deck_path.read_text(encoding="utf-8"))

    assert payload["_counters"] == {"slides": 1, "nodes": 1}
    assert payload["template_manifest"] == "templates/demo/manifest.json"
    assert "computed" not in payload["slides"][0]
    assert restored == original


def test_resolve_manifest_path_returns_absolute_path(tmp_path: Path) -> None:
    deck_path = tmp_path / "nested" / "deck.json"
    deck_path.parent.mkdir()
    deck = build_deck(template_manifest="templates/demo/manifest.json")

    resolved = resolve_manifest_path(str(deck_path), deck)

    assert resolved == str(deck_path.parent / "templates" / "demo" / "manifest.json")


def test_resolve_manifest_path_returns_none_when_manifest_missing(tmp_path: Path) -> None:
    deck = build_deck()

    assert resolve_manifest_path(str(tmp_path / "deck.json"), deck) is None


def test_read_deck_prefers_computed_sidecar_when_present(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_deck(revision=4))

    deck = read_deck(str(deck_path))
    deck.slides[0].computed["n-1"].font_size_pt = 16.0
    write_deck(str(deck_path), deck, expected_revision=4)

    loaded = read_deck(str(deck_path))

    assert loaded.slides[0].computed["n-1"].font_size_pt == 16.0
    assert "computed" not in json.loads(deck_path.read_text(encoding="utf-8"))["slides"][0]


def test_read_deck_ignores_stale_computed_sidecar(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    deck = build_deck(revision=2)
    write_raw_deck(deck_path, deck)
    write_computed_deck(str(deck_path), deck)

    updated_payload = json.loads(deck_path.read_text(encoding="utf-8"))
    updated_payload["revision"] = 9
    deck_path.write_text(f"{json.dumps(updated_payload, indent=2)}\n", encoding="utf-8")

    loaded = read_deck(str(deck_path))

    assert loaded.revision == 9
    assert loaded.slides[0].computed == {}
