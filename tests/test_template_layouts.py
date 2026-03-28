from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_slides.errors import AgentSlidesError, INVALID_LAYOUT
from agent_slides.io.sidecar import mutate_deck
from agent_slides.model import (
    BuiltinLayoutProvider,
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


def _build_variant_manifest(base_dir: Path, *, body_bounds: list[dict[str, float]]) -> Path:
    template_path = base_dir / "templates" / "variant" / "variant-template.pptx"
    manifest_path = base_dir / "templates" / "variant" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")

    placeholders = [
        {
            "idx": 0,
            "type": "TITLE",
            "name": "Title",
            "bounds": {"x": 72, "y": 48, "w": 576, "h": 72},
        }
    ]
    for index, bounds in enumerate(body_bounds, start=1):
        placeholders.append(
            {
                "idx": index,
                "type": "BODY",
                "name": f"Body {index}",
                "bounds": bounds,
            }
        )

    manifest_path.write_text(
        json.dumps(
            {
                "name": "variant-template",
                "source": "variant-template.pptx",
                "source_hash": "variant123",
                "theme": {
                    "name": "variant-theme",
                    "colors": {
                        "primary": "#101820",
                        "secondary": "#203040",
                        "accent": "#ff6600",
                        "background": "#faf7f2",
                        "text": "#1f1f1f",
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
                        "slug": "peer_bodies",
                        "usable": True,
                        "placeholders": placeholders,
                        "slot_mapping": {
                            "heading": 0,
                            **{f"body_{index}": index for index in range(1, len(body_bounds) + 1)},
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


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


def test_template_layout_registry_infers_slot_metadata_from_placeholder_topology(tmp_path: Path) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 180, "h": 220},
            {"x": 270, "y": 156, "w": 180, "h": 220},
            {"x": 468, "y": 156, "w": 180, "h": 220},
        ],
    )

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("peer_bodies")

    assert layout.slots["heading"].alignment_group == "top"
    assert layout.slots["heading"].reading_order == 0
    assert layout.slots["body_1"].peer_group == "columns"
    assert layout.slots["body_1"].alignment_group == "content"
    assert layout.slots["body_1"].reading_order == 1
    assert layout.slots["body_2"].peer_group == "columns"
    assert layout.slots["body_3"].peer_group == "columns"


def test_template_layout_registry_generates_semantic_variants_for_peer_bodies(tmp_path: Path) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 180, "h": 220},
            {"x": 270, "y": 156, "w": 180, "h": 220},
            {"x": 468, "y": 156, "w": 180, "h": 220},
        ],
    )
    registry = TemplateLayoutRegistry(str(manifest_path))

    variants = registry.get_variants("peer_bodies")

    assert [variant.name for variant in variants] == ["two_col", "three_col"]
    assert list(variants[0].slots) == ["heading", "col1", "col2"]
    assert variants[0].slots["col1"].peer_group == "columns"
    assert list(variants[1].slots) == ["heading", "col1", "col2", "col3"]


def test_template_layout_registry_skips_variants_when_peer_invariants_fail(tmp_path: Path) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 180, "h": 220},
            {"x": 270, "y": 196, "w": 180, "h": 220},
            {"x": 468, "y": 156, "w": 180, "h": 260},
        ],
    )
    registry = TemplateLayoutRegistry(str(manifest_path))

    assert registry.get_variants("peer_bodies") == []


def test_template_layout_registry_skips_variants_when_solved_widths_differ(tmp_path: Path) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 180, "h": 220},
            {"x": 270, "y": 156, "w": 210, "h": 220},
            {"x": 508, "y": 156, "w": 140, "h": 220},
        ],
    )
    registry = TemplateLayoutRegistry(str(manifest_path))

    assert registry.get_variants("peer_bodies") == []


def test_layout_providers_expose_get_variants_consistently(tmp_path: Path) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 279, "h": 240},
            {"x": 369, "y": 156, "w": 279, "h": 240},
        ],
    )
    builtin = BuiltinLayoutProvider()
    template = TemplateLayoutRegistry(str(manifest_path))

    assert builtin.get_variants("two_col") == []
    assert [variant.name for variant in template.get_variants("peer_bodies")] == ["title_content", "two_col"]


def test_mutate_deck_uses_template_layout_registry_when_manifest_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reflow_module = __import__("agent_slides.engine.reflow", fromlist=["reflow_deck"])
    manifest_path = _build_manifest(tmp_path)
    deck_path = tmp_path / "deck.json"
    deck = _build_template_deck(str(manifest_path.relative_to(tmp_path)))
    _write_deck(deck_path, deck)

    seen_provider_types: list[type[object]] = []
    seen_layouts: list[list[str]] = []

    def fake_reflow(updated_deck: Deck, provider, **_: object) -> None:
        assert updated_deck.revision == 5
        seen_provider_types.append(type(provider))
        assert isinstance(provider, TemplateLayoutRegistryImpl)
        seen_layouts.append(provider.list_layouts())

    monkeypatch.setattr(reflow_module, "reflow_deck", fake_reflow)

    updated_deck, result = mutate_deck(
        str(deck_path),
        lambda current_deck, provider: ("ok", provider.get_layout(current_deck.slides[0].layout).name),
    )

    assert updated_deck.revision == 5
    assert result == ("ok", "template_title")
    assert seen_provider_types == [TemplateLayoutRegistryImpl]
    assert seen_layouts == [["template_title"]]
