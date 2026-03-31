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
from agent_slides.model.template_layouts import (
    TemplateLayoutRegistry as TemplateLayoutRegistryImpl,
)


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
                                "bounds": {
                                    "x": 72,
                                    "y": 64,
                                    "width": 560,
                                    "height": 96,
                                },
                            },
                            "body": {
                                "role": "body",
                                "bounds": {
                                    "x": 72,
                                    "y": 180,
                                    "width": 560,
                                    "height": 220,
                                },
                            },
                        },
                    },
                    {
                        "slug": "skip_me",
                        "usable": False,
                        "slot_mapping": {
                            "body": {
                                "role": "body",
                                "bounds": {
                                    "x": 10,
                                    "y": 10,
                                    "width": 100,
                                    "height": 100,
                                },
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


def _build_heading_only_manifest(
    base_dir: Path,
    *,
    color_zones: list[dict[str, object]] | None = None,
    editable_regions: list[dict[str, object]] | None = None,
) -> Path:
    template_path = base_dir / "templates" / "heading-only" / "template.pptx"
    manifest_path = base_dir / "templates" / "heading-only" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")
    manifest_path.write_text(
        json.dumps(
            {
                "name": "heading-only-template",
                "source": "template.pptx",
                "source_hash": "heading123",
                "theme": {
                    "name": "heading-only-theme",
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
                        "slug": "green_highlight",
                        "usable": True,
                        **(
                            {"color_zones": color_zones}
                            if color_zones is not None
                            else {}
                        ),
                        **(
                            {"editable_regions": editable_regions}
                            if editable_regions is not None
                            else {}
                        ),
                        "slot_mapping": {
                            "heading": {
                                "role": "heading",
                                "bounds": {
                                    "x": 72,
                                    "y": 64,
                                    "width": 560,
                                    "height": 72,
                                },
                            }
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _build_color_zone_manifest(base_dir: Path) -> Path:
    template_path = base_dir / "templates" / "zones" / "template.pptx"
    manifest_path = base_dir / "templates" / "zones" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")
    manifest_path.write_text(
        json.dumps(
            {
                "name": "zoned-template",
                "source": "template.pptx",
                "source_hash": "zones123",
                "theme": {
                    "name": "zoned-theme",
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
                        "slug": "two_panel_story",
                        "usable": True,
                        "color_zones": [
                            {
                                "region": "panel_0",
                                "left": 0,
                                "width": 360,
                                "bg_color": "FFFFFF",
                                "text_color": "333333",
                            },
                            {
                                "region": "panel_1",
                                "left": 360,
                                "width": 360,
                                "bg_color": "00A651",
                                "text_color": "FFFFFF",
                            },
                        ],
                        "slot_mapping": {
                            "heading": {
                                "role": "heading",
                                "bounds": {
                                    "x": 72,
                                    "y": 64,
                                    "width": 220,
                                    "height": 96,
                                },
                            },
                            "body": {
                                "role": "body",
                                "bounds": {
                                    "x": 420,
                                    "y": 180,
                                    "width": 220,
                                    "height": 220,
                                },
                            },
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _build_heading_only_color_zone_manifest(base_dir: Path) -> Path:
    template_path = base_dir / "templates" / "heading-zones" / "template.pptx"
    manifest_path = base_dir / "templates" / "heading-zones" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")
    manifest_path.write_text(
        json.dumps(
            {
                "name": "heading-zones-template",
                "source": "template.pptx",
                "source_hash": "heading-zones123",
                "theme": {
                    "name": "heading-zones-theme",
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
                        "slug": "green_highlight",
                        "usable": True,
                        "color_zones": [
                            {
                                "region": "panel_0",
                                "left": 0,
                                "width": 360,
                                "bg_color": "FFFFFF",
                                "text_color": "333333",
                            },
                            {
                                "region": "panel_1",
                                "left": 360,
                                "width": 360,
                                "bg_color": "00A651",
                                "text_color": "FFFFFF",
                            },
                        ],
                        "editable_regions": [
                            {
                                "name": "content_area",
                                "left": 390,
                                "top": 170,
                                "width": 270,
                                "height": 240,
                                "source": "visual_inference_no_placeholders",
                            }
                        ],
                        "slot_mapping": {
                            "heading": {
                                "role": "heading",
                                "bounds": {
                                    "x": 72,
                                    "y": 64,
                                    "width": 220,
                                    "height": 72,
                                },
                            }
                        },
                    }
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


def _build_variant_manifest(
    base_dir: Path, *, body_bounds: list[dict[str, float]]
) -> Path:
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
                            **{
                                f"body_{index}": index
                                for index in range(1, len(body_bounds) + 1)
                            },
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_template_layout_registry_loads_manifest_and_exposes_theme(
    tmp_path: Path,
) -> None:
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


def test_template_layout_registry_applies_zone_colors_to_slots(tmp_path: Path) -> None:
    manifest_path = _build_color_zone_manifest(tmp_path)

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("two_panel_story")

    assert layout.slots["heading"].bg_color == "#FFFFFF"
    assert layout.slots["heading"].text_color == "#333333"
    assert layout.slots["body"].bg_color == "#00A651"
    assert layout.slots["body"].text_color == "#FFFFFF"


def test_template_layout_registry_invalid_layout_raises_invalid_layout(
    tmp_path: Path,
) -> None:
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


def test_template_layout_registry_synthesizes_virtual_body_slot_for_heading_only_layout(
    tmp_path: Path,
) -> None:
    manifest_path = _build_heading_only_manifest(
        tmp_path,
        color_zones=[
            {
                "region": "panel_0",
                "left": 0.0,
                "width": 420.0,
                "bg_color": "FFFFFF",
                "text_color": "333333",
                "editable_below": {
                    "left": 0.0,
                    "top": 90.0,
                    "width": 420.0,
                    "height": 450.0,
                },
            },
            {
                "region": "gap_0",
                "left": 420.0,
                "width": 120.0,
                "bg_color": "FFFFFF",
                "text_color": "333333",
            },
            {
                "region": "panel_1",
                "left": 540.0,
                "width": 420.0,
                "bg_color": "00A651",
                "text_color": "FFFFFF",
            },
        ],
        editable_regions=[
            {
                "name": "content_area",
                "left": 540.0,
                "top": 170.0,
                "width": 420.0,
                "height": 320.0,
                "source": "visual_inference_no_placeholders",
            }
        ],
    )

    registry = TemplateLayoutRegistry(str(manifest_path))
    layout = registry.get_layout("green_highlight")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert registry.get_slot_names("green_highlight") == ["heading", "body"]
    assert "body" not in manifest["layouts"][0]["slot_mapping"]
    assert layout.slots["body"].role == "body"
    # Visual-inference editable region at (540, 170, 420, 320) is preferred
    # over editable_below. Left stays at 540 (above min margin). Top is
    # clamped to heading_bottom + heading_height = 64+72+72 = 208.
    assert layout.slots["body"].x == 540.0
    assert layout.slots["body"].y == 208.0
    assert layout.slots["body"].width == 420.0
    assert layout.slots["body"].height == pytest.approx(490.0 - 208.0)
    # Content slot is suppressed when virtual body exists to avoid overlap
    assert "content" not in layout.slots


def test_template_layout_registry_uses_editable_regions_when_zone_lacks_editable_below(
    tmp_path: Path,
) -> None:
    manifest_path = _build_heading_only_manifest(
        tmp_path,
        color_zones=[
            {
                "region": "panel_0",
                "left": 0.0,
                "width": 420.0,
                "bg_color": "FFFFFF",
                "text_color": "333333",
            }
        ],
        editable_regions=[
            {
                "name": "above_heading",
                "left": 72.0,
                "top": 24.0,
                "width": 220.0,
                "height": 24.0,
                "source": "visual_inference_no_placeholders",
            },
            {
                "name": "body_area_small",
                "left": 96.0,
                "top": 180.0,
                "width": 200.0,
                "height": 180.0,
                "source": "visual_inference_no_placeholders",
            },
            {
                "name": "body_area_large",
                "left": 320.0,
                "top": 180.0,
                "width": 280.0,
                "height": 240.0,
                "source": "visual_inference_no_placeholders",
            },
            {
                "name": "ignored_source",
                "left": 20.0,
                "top": 220.0,
                "width": 500.0,
                "height": 240.0,
                "source": "placeholder_geometry",
            },
        ],
    )

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("green_highlight")

    assert layout.slots["body"].x == 320.0
    # Top clamped to heading_bottom + heading_height = 64+72+72 = 208
    assert layout.slots["body"].y == 208.0
    assert layout.slots["body"].width == 280.0
    # Height reduced: original bottom (180+240=420) - clamped top (208) = 212
    assert layout.slots["body"].height == pytest.approx(420.0 - 208.0)


def test_template_layout_registry_falls_back_to_offset_formula_without_manifest_regions(
    tmp_path: Path,
) -> None:
    manifest_path = _build_heading_only_manifest(tmp_path)

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("green_highlight")

    assert layout.slots["body"].x == 72.0
    assert layout.slots["body"].y == 262.0
    assert layout.slots["body"].width == 600.0
    assert layout.slots["body"].height == 230.0


def test_template_layout_registry_uses_editable_region_and_zone_colors_for_virtual_body(
    tmp_path: Path,
) -> None:
    manifest_path = _build_heading_only_color_zone_manifest(tmp_path)

    layout = TemplateLayoutRegistry(str(manifest_path)).get_layout("green_highlight")

    assert layout.slots["body"].x == 390.0
    # Top clamped to heading_bottom + heading_height = 64+72+72 = 208
    assert layout.slots["body"].y == 208.0
    assert layout.slots["body"].width == 270.0
    assert layout.slots["body"].height == pytest.approx(410.0 - 208.0)
    assert layout.slots["body"].bg_color == "#00A651"
    assert layout.slots["body"].text_color == "#FFFFFF"


def test_template_layout_registry_infers_slot_metadata_from_placeholder_topology(
    tmp_path: Path,
) -> None:
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


def test_template_layout_registry_generates_semantic_variants_for_peer_bodies(
    tmp_path: Path,
) -> None:
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


def test_template_layout_registry_generates_four_column_variant_for_peer_bodies(
    tmp_path: Path,
) -> None:
    manifest_path = _build_variant_manifest(
        tmp_path,
        body_bounds=[
            {"x": 72, "y": 156, "w": 126, "h": 220},
            {"x": 216, "y": 156, "w": 126, "h": 220},
            {"x": 360, "y": 156, "w": 126, "h": 220},
            {"x": 504, "y": 156, "w": 126, "h": 220},
        ],
    )
    registry = TemplateLayoutRegistry(str(manifest_path))

    variants = registry.get_variants("peer_bodies")

    assert [variant.name for variant in variants] == [
        "two_col",
        "three_col",
        "four_col",
    ]
    assert list(variants[-1].slots) == ["heading", "col1", "col2", "col3", "col4"]
    assert all(
        variants[-1].slots[f"col{index}"].peer_group == "columns"
        for index in range(1, 5)
    )


def test_template_layout_registry_skips_variants_when_peer_invariants_fail(
    tmp_path: Path,
) -> None:
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


def test_template_layout_registry_skips_variants_when_solved_widths_differ(
    tmp_path: Path,
) -> None:
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

    assert [variant.name for variant in builtin.get_variants("two_col")] == [
        "title_content"
    ]
    assert [variant.name for variant in template.get_variants("peer_bodies")] == [
        "title_content",
        "two_col",
    ]


def _build_mixed_text_image_manifest(base_dir: Path) -> Path:
    template_path = base_dir / "templates" / "mixed" / "mixed-template.pptx"
    manifest_path = base_dir / "templates" / "mixed" / "manifest.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_bytes(b"pptx")

    manifest_path.write_text(
        json.dumps(
            {
                "name": "mixed-template",
                "source": "mixed-template.pptx",
                "source_hash": "mixed123",
                "theme": {
                    "name": "mixed-theme",
                    "colors": {
                        "primary": "#101820",
                        "secondary": "#203040",
                        "accent": "#ff6600",
                        "background": "#faf7f2",
                        "text": "#1f1f1f",
                    },
                    "fonts": {"heading": "Aptos Display", "body": "Aptos"},
                    "spacing": {"base_unit": 12, "margin": 48, "gutter": 18},
                },
                "layouts": [
                    {
                        "slug": "intro_with_image",
                        "usable": True,
                        "placeholders": [
                            {
                                "idx": 0,
                                "type": "TITLE",
                                "name": "Title",
                                "bounds": {"x": 72, "y": 48, "w": 576, "h": 72},
                            },
                            {
                                "idx": 1,
                                "type": "BODY",
                                "name": "Body",
                                "bounds": {"x": 72, "y": 156, "w": 270, "h": 300},
                            },
                            {
                                "idx": 2,
                                "type": "PICTURE",
                                "name": "Image",
                                "bounds": {"x": 360, "y": 156, "w": 288, "h": 300},
                            },
                        ],
                        "slot_mapping": {"heading": 0, "body": 1, "image": 2},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_template_layout_registry_generates_image_free_variant(tmp_path: Path) -> None:
    manifest_path = _build_mixed_text_image_manifest(tmp_path)
    registry = TemplateLayoutRegistry(str(manifest_path))

    variants = registry.get_variants("intro_with_image")

    variant_names = [variant.name for variant in variants]
    assert "title_content" in variant_names

    title_content = next(v for v in variants if v.name == "title_content")
    assert list(title_content.slots) == ["heading", "body"]
    body_slot = title_content.slots["body"]
    assert body_slot.width is not None
    assert body_slot.width > 270, "body should expand to cover the image slot's width"


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
        lambda current_deck, provider: (
            "ok",
            provider.get_layout(current_deck.slides[0].layout).name,
        ),
    )

    assert updated_deck.revision == 5
    assert result == ("ok", "template_title")
    assert seen_provider_types == [TemplateLayoutRegistryImpl]
    assert seen_layouts == [["template_title"]]
