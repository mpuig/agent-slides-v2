from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT
from agent_slides.io.sidecar import mutate_deck
from agent_slides.model import (
    Counters,
    Deck,
    Node,
    Slide,
    TemplateLayoutRegistry,
)
from agent_slides.model.template_layouts import TemplateLayoutRegistry as TemplateLayoutRegistryImpl


def _build_manifest(base_dir: Path) -> Path:
    template_path = base_dir / "templates" / "demo" / "demo-template.pptx"
    manifest_path = base_dir / "templates" / "demo" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")
    manifest_path.write_text(
        json.dumps(
            {
                "name": "demo-template",
                "source": "demo-template.pptx",
                "source_hash": "abc123",
                "theme": {
                    "name": "learned-theme",
                    "colors": {
                        "primary": "#101820",
                        "secondary": "#203040",
                        "accent": "#ff6600",
                        "background": "#faf7f2",
                        "text": "#1f1f1f",
                        "heading_text": "#111111",
                        "subtle_text": "#666666",
                    },
                    "fonts": {
                        "heading": "Aptos Display",
                        "body": "Aptos",
                    },
                    "spacing": {
                        "base_unit": 12,
                        "margin": 48,
                        "gutter": 18,
                    },
                },
                "layouts": [
                    {
                        "slug": "template_title",
                        "usable": True,
                        "slot_mapping": {
                            "heading": {
                                "role": "heading",
                                "bounds": {"x": 72, "y": 64, "width": 560, "height": 96},
                            },
                            "body": {
                                "role": "body",
                                "bounds": {"x": 72, "y": 180, "width": 560, "height": 220},
                            },
                        },
                    },
                    {
                        "slug": "skip_me",
                        "usable": False,
                        "slot_mapping": {
                            "body": {
                                "role": "body",
                                "bounds": {"x": 10, "y": 10, "width": 100, "height": 100},
                            }
                        },
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _build_template_deck(manifest_relpath: str) -> Deck:
    return Deck(
        deck_id="deck-template",
        revision=4,
        theme="default",
        design_rules="default",
        template_manifest=manifest_relpath,
        slides=[
            Slide(
                slide_id="s-1",
                layout="template_title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Template heading",
                    )
                ],
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def _write_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def test_template_layout_registry_loads_manifest_and_exposes_theme(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)

    registry = TemplateLayoutRegistry(str(manifest_path))

    assert registry.list_layouts() == ["template_title"]
    assert registry.get_slot_names("template_title") == ["heading", "body"]
    assert registry.source_path == str(manifest_path.parent / "demo-template.pptx")
    assert registry.source_hash == "abc123"
    assert registry.theme.name == "learned-theme"
    assert registry.theme.colors.accent == "#ff6600"
    assert registry.theme.fonts.heading == "Aptos Display"
    assert registry.theme.spacing.margin == 48


def test_template_layout_registry_returns_bounds_backed_layout(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("template_title")

    assert layout.name == "template_title"
    assert layout.slots["heading"].x == 72
    assert layout.slots["heading"].y == 64
    assert layout.slots["heading"].width == 560
    assert layout.slots["heading"].height == 96
    assert layout.slots["body"].role == "body"


def test_template_layout_registry_invalid_layout_raises_invalid_layout(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)
    registry = TemplateLayoutRegistry(str(manifest_path))

    with pytest.raises(AgentSlidesError) as exc_info:
        registry.get_layout("invalid")

    assert exc_info.value.code == INVALID_LAYOUT


def test_template_layout_registry_uses_default_text_fitting(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)
    registry = TemplateLayoutRegistry(str(manifest_path))

    heading_fit = registry.get_text_fitting("template_title", "heading")
    body_fit = registry.get_text_fitting("template_title", "body")

    assert heading_fit.default_size == 32.0
    assert heading_fit.min_size == 24.0
    assert body_fit.default_size == 18.0
    assert body_fit.min_size == 10.0


def test_mutate_deck_uses_template_layout_registry_when_manifest_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_manifest(tmp_path)
    deck_path = tmp_path / "deck.json"
    deck = _build_template_deck(str(manifest_path.relative_to(tmp_path)))
    _write_deck(deck_path, deck)

    seen_provider_types: list[type[object]] = []
    seen_layouts: list[list[str]] = []

    def fake_reflow(updated_deck: Deck, *, layout_provider: object | None = None) -> None:
        seen_provider_types.append(type(layout_provider))
        assert isinstance(layout_provider, TemplateLayoutRegistryImpl)
        seen_layouts.append(layout_provider.list_layouts())

    monkeypatch.setattr("agent_slides.engine.reflow.reflow_deck", fake_reflow)

    updated_deck, result = mutate_deck(str(deck_path), lambda current_deck: ("ok", current_deck.slides[0].layout))

    assert updated_deck.revision == 5
    assert result == ("ok", "template_title")
    assert seen_provider_types == [TemplateLayoutRegistryImpl]
    assert seen_layouts == [["template_title"]]
