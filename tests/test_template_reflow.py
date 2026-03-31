from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_slides.engine.reflow import reflow_deck
from agent_slides.io.sidecar import mutate_deck
from agent_slides.model import (
    ChartSeries,
    ChartSpec,
    Counters,
    Deck,
    Node,
    Slide,
    TemplateLayoutRegistry,
)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def write_raw_deck(path: Path, deck: Deck) -> None:
    payload = json.loads(deck.model_dump_json(by_alias=True))
    for slide in payload["slides"]:
        slide.pop("computed", None)
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def make_manifest() -> dict[str, object]:
    return {
        "name": "template",
        "source": "template.pptx",
        "source_hash": "abc123",
        "layouts": [
            {
                "slug": "photo_story",
                "usable": True,
                "slot_mapping": {
                    "heading": {
                        "role": "heading",
                        "bounds": {
                            "x": 12.0,
                            "y": 18.0,
                            "width": 280.0,
                            "height": 48.0,
                        },
                    },
                    "image": {
                        "role": "image",
                        "bounds": {
                            "x": 312.0,
                            "y": 24.0,
                            "width": 180.0,
                            "height": 200.0,
                        },
                    },
                    "body": {
                        "role": "body",
                        "bounds": {
                            "x": 18.0,
                            "y": 96.0,
                            "width": 260.0,
                            "height": 160.0,
                        },
                    },
                },
            }
        ],
        "theme": {
            "colors": {
                "primary": "#112233",
                "secondary": "#445566",
                "accent": "#778899",
                "text": "#101010",
                "heading_text": "#202020",
                "subtle_text": "#606060",
                "background": "#FAFAFA",
            },
            "fonts": {
                "heading": "Aptos Display",
                "body": "Aptos",
            },
            "spacing": {
                "base_unit": 10.0,
                "margin": 60.0,
                "gutter": 20.0,
            },
        },
    }


def make_heading_only_manifest(
    *,
    color_zones: list[dict[str, object]] | None = None,
    editable_regions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "name": "template",
        "source": "template.pptx",
        "source_hash": "abc123",
        "layouts": [
            {
                "slug": "green_highlight",
                "usable": True,
                **({"color_zones": color_zones} if color_zones is not None else {}),
                **(
                    {"editable_regions": editable_regions}
                    if editable_regions is not None
                    else {}
                ),
                "slot_mapping": {
                    "heading": {
                        "role": "heading",
                        "bounds": {
                            "x": 72.0,
                            "y": 64.0,
                            "width": 560.0,
                            "height": 72.0,
                        },
                    }
                },
            }
        ],
        "theme": {
            "colors": {
                "primary": "#112233",
                "secondary": "#445566",
                "accent": "#778899",
                "text": "#101010",
                "heading_text": "#202020",
                "subtle_text": "#606060",
                "background": "#FAFAFA",
            },
            "fonts": {
                "heading": "Aptos Display",
                "body": "Aptos",
            },
            "spacing": {
                "base_unit": 10.0,
                "margin": 48.0,
                "gutter": 18.0,
            },
        },
    }


def make_color_zone_manifest() -> dict[str, object]:
    return {
        "name": "template",
        "source": "template.pptx",
        "source_hash": "abc123",
        "layouts": [
            {
                "slug": "two_panel_story",
                "usable": True,
                "color_zones": [
                    {
                        "region": "panel_0",
                        "left": 0.0,
                        "width": 360.0,
                        "bg_color": "FFFFFF",
                        "text_color": "333333",
                    },
                    {
                        "region": "panel_1",
                        "left": 360.0,
                        "width": 360.0,
                        "bg_color": "00A651",
                        "text_color": "FFFFFF",
                    },
                ],
                "slot_mapping": {
                    "heading": {
                        "role": "heading",
                        "bounds": {
                            "x": 12.0,
                            "y": 18.0,
                            "width": 280.0,
                            "height": 48.0,
                        },
                    },
                    "body": {
                        "role": "body",
                        "bounds": {
                            "x": 420.0,
                            "y": 96.0,
                            "width": 220.0,
                            "height": 160.0,
                        },
                    },
                },
            }
        ],
        "theme": {
            "colors": {
                "primary": "#112233",
                "secondary": "#445566",
                "accent": "#778899",
                "text": "#101010",
                "heading_text": "#202020",
                "subtle_text": "#606060",
                "background": "#FAFAFA",
            },
            "fonts": {
                "heading": "Aptos Display",
                "body": "Aptos",
            },
            "spacing": {
                "base_unit": 10.0,
                "margin": 60.0,
                "gutter": 20.0,
            },
        },
    }


def test_reflow_deck_uses_manifest_bounds_theme_and_text_fitting(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = tmp_path / "template.manifest.json"
    (tmp_path / "template.pptx").write_bytes(b"pptx")
    write_json(manifest_path, make_manifest())
    image_path = tmp_path / "hero.png"
    image_path.write_bytes(b"png")

    fit_calls: list[
        tuple[float, float, float, float, str, str, list[float] | None]
    ] = []

    def fake_fit_text(
        *,
        text,
        width: float,
        height: float,
        default_size: float,
        min_size: float,
        role: str,
        font_family: str | None = None,
        ladder: list[float] | None = None,
        use_precise: bool = False,
    ):
        assert use_precise is False
        fit_calls.append(
            (width, height, default_size, min_size, role, font_family or "", ladder)
        )
        return (26.0, False) if default_size == 32.0 else (14.0, True)

    monkeypatch.setattr("agent_slides.engine.reflow.fit_text", fake_fit_text)

    deck = Deck(
        deck_id="deck-template",
        revision=7,
        theme="default",
        design_rules="default",
        template_manifest="template.manifest.json",
        slides=[
            Slide(
                slide_id="s-1",
                layout="photo_story",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Long heading",
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="body",
                        type="text",
                        content="Long body copy",
                    ),
                    Node(
                        node_id="n-3",
                        slot_binding="image",
                        type="image",
                        image_path=str(image_path),
                    ),
                    Node(
                        node_id="n-4",
                        slot_binding=None,
                        type="text",
                        content="Leave unbound",
                    ),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=4),
    )

    registry = TemplateLayoutRegistry(manifest_path)

    reflow_deck(deck, registry)

    computed = deck.slides[0].computed
    assert set(computed) == {"n-1", "n-2", "n-3"}

    heading = computed["n-1"]
    assert (heading.x, heading.y, heading.width, heading.height) == (
        12.0,
        18.0,
        280.0,
        48.0,
    )
    assert heading.font_size_pt == 26.0
    assert heading.font_family == "Aptos Display"
    assert heading.color == "#202020"
    assert heading.font_bold is True
    assert heading.revision == 7

    body = computed["n-2"]
    assert (body.x, body.y, body.width, body.height) == (18.0, 96.0, 260.0, 160.0)
    assert body.font_size_pt == 14.0
    assert body.font_family == "Aptos"
    assert body.color == "#101010"
    assert body.font_bold is False
    assert body.text_overflow is True
    assert body.bg_color == "#FAFAFA"

    image = computed["n-3"]
    assert (image.x, image.y, image.width, image.height) == (312.0, 24.0, 180.0, 200.0)
    assert image.font_size_pt == 0.0
    assert image.content_type == "image"
    assert image.font_family == "Aptos"
    assert image.color == "#101010"

    # The reflow engine extends ladders when adjusted min_size is below the
    # lowest configured step, so heading may include extra steps (20.0, 16.0)
    # for template slots with tight bounds.
    heading_call = fit_calls[0]
    body_call = fit_calls[1]
    assert heading_call[0] == pytest.approx(280.0)
    assert heading_call[1] == pytest.approx(48.0)
    assert heading_call[2] == pytest.approx(32.0)
    assert heading_call[3] <= 17.0  # min_size derived from placeholder height
    assert heading_call[4] == "heading"
    assert heading_call[5] == "Aptos Display"
    assert heading_call[6][0] == 32.0  # starts at default
    assert heading_call[6][-1] <= 17.0  # reaches min
    assert body_call[:6] == (260.0, 160.0, 18.0, 10.0, "body", "Aptos")
    assert body_call[6][0] == 18.0
    assert body_call[6][-1] <= 10.0


def test_mutate_deck_reflows_template_manifests_with_unified_reflow(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = tmp_path / "template.manifest.json"
    (tmp_path / "template.pptx").write_bytes(b"pptx")
    write_json(manifest_path, make_manifest())
    deck_path = tmp_path / "deck.json"
    write_raw_deck(
        deck_path,
        Deck(
            deck_id="deck-1",
            revision=2,
            theme="default",
            design_rules="default",
            template_manifest="template.manifest.json",
            slides=[
                Slide(
                    slide_id="s-1",
                    layout="photo_story",
                    nodes=[
                        Node(
                            node_id="n-1",
                            slot_binding="heading",
                            type="text",
                            content="Title",
                        )
                    ],
                )
            ],
            counters=Counters(slides=1, nodes=1),
        ),
    )

    reflow_calls: list[tuple[int, str]] = []

    def fake_reflow(deck: Deck, provider, **_: object) -> None:
        reflow_calls.append((deck.revision, provider.source_path))

    monkeypatch.setattr("agent_slides.engine.reflow.reflow_deck", fake_reflow)

    def mutate(deck: Deck, provider) -> str:
        assert isinstance(provider, TemplateLayoutRegistry)
        deck.theme = "corporate"
        return "ok"

    updated_deck, result = mutate_deck(str(deck_path), mutate)

    assert result == "ok"
    assert updated_deck.revision == 3
    assert updated_deck.theme == "corporate"
    assert reflow_calls == [(3, str((tmp_path / "template.pptx").resolve()))]


def test_reflow_deck_prefers_zone_text_colors_over_theme_colors(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = tmp_path / "template.manifest.json"
    (tmp_path / "template.pptx").write_bytes(b"pptx")
    write_json(manifest_path, make_color_zone_manifest())

    def fake_fit_text(
        *,
        text,
        width: float,
        height: float,
        default_size: float,
        min_size: float,
        role: str,
        font_family: str | None = None,
        ladder: list[float] | None = None,
        use_precise: bool = False,
    ):
        return (26.0, False) if role == "heading" else (14.0, False)

    monkeypatch.setattr("agent_slides.engine.reflow.fit_text", fake_fit_text)

    deck = Deck(
        deck_id="deck-template",
        revision=8,
        theme="default",
        design_rules="default",
        template_manifest="template.manifest.json",
        slides=[
            Slide(
                slide_id="s-1",
                layout="two_panel_story",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Long heading",
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="body",
                        type="text",
                        content="Long body copy",
                    ),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )

    registry = TemplateLayoutRegistry(manifest_path)

    reflow_deck(deck, registry)

    heading = deck.slides[0].computed["n-1"]
    body = deck.slides[0].computed["n-2"]

    assert heading.color == "#333333"
    assert heading.bg_color == "#FFFFFF"
    assert body.color == "#FFFFFF"
    assert body.bg_color == "#00A651"


def test_reflow_deck_uses_virtual_body_slot_bounds_for_heading_only_templates(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = tmp_path / "template.manifest.json"
    (tmp_path / "template.pptx").write_bytes(b"pptx")
    write_json(
        manifest_path,
        make_heading_only_manifest(
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
        ),
    )

    fit_calls: list[
        tuple[float, float, float, float, str, str, list[float] | None]
    ] = []

    def fake_fit_text(
        *,
        text,
        width: float,
        height: float,
        default_size: float,
        min_size: float,
        role: str,
        font_family: str | None = None,
        ladder: list[float] | None = None,
        use_precise: bool = False,
    ):
        assert use_precise is False
        fit_calls.append(
            (width, height, default_size, min_size, role, font_family or "", ladder)
        )
        return (26.0, False) if role == "heading" else (14.0, False)

    monkeypatch.setattr("agent_slides.engine.reflow.fit_text", fake_fit_text)

    deck = Deck(
        deck_id="deck-template",
        revision=7,
        theme="default",
        design_rules="default",
        template_manifest="template.manifest.json",
        slides=[
            Slide(
                slide_id="s-1",
                layout="green_highlight",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Long heading",
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="body",
                        type="text",
                        content="Long body copy",
                    ),
                ],
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )

    registry = TemplateLayoutRegistry(manifest_path)

    reflow_deck(deck, registry)

    computed = deck.slides[0].computed
    assert set(computed) == {"n-1", "n-2"}

    body = computed["n-2"]
    # Virtual body top is clamped to heading_bottom + gutter (64+72+18=154)
    assert (body.x, body.y, body.width, body.height) == (0.0, 154.0, 420.0, 386.0)
    assert body.font_size_pt == 14.0
    assert body.font_family == "Aptos"
    assert body.color == "#333333"
    assert body.bg_color == "#FFFFFF"
    assert body.text_overflow is False

    body_call = fit_calls[1]
    assert body_call[:6] == (420.0, 386.0, 18.0, 10.0, "body", "Aptos")


def test_reflow_deck_places_template_chart_nodes_in_virtual_content_slot(
    tmp_path: Path,
) -> None:
    """When a layout has a native body slot, a content slot is created from the
    editable region so charts can be placed there independently."""
    manifest_path = tmp_path / "template.manifest.json"
    (tmp_path / "template.pptx").write_bytes(b"pptx")
    write_json(
        manifest_path,
        {
            "name": "template",
            "source": "template.pptx",
            "source_hash": "abc123",
            "layouts": [
                {
                    "slug": "chart_layout",
                    "usable": True,
                    "editable_regions": [
                        {
                            "name": "chart_area",
                            "left": 540.0,
                            "top": 170.0,
                            "width": 420.0,
                            "height": 320.0,
                            "source": "visual_inference_no_placeholders",
                        }
                    ],
                    "slot_mapping": {
                        "heading": {
                            "role": "heading",
                            "bounds": {
                                "x": 72.0,
                                "y": 64.0,
                                "width": 560.0,
                                "height": 72.0,
                            },
                        },
                        "body": {
                            "role": "body",
                            "bounds": {
                                "x": 72.0,
                                "y": 150.0,
                                "width": 400.0,
                                "height": 300.0,
                            },
                        },
                    },
                }
            ],
            "theme": make_heading_only_manifest()["theme"],
        },
    )

    deck = Deck(
        deck_id="deck-template-chart",
        revision=7,
        theme="default",
        design_rules="default",
        template_manifest="template.manifest.json",
        slides=[
            Slide(
                slide_id="s-1",
                layout="chart_layout",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Quarterly performance",
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="content",
                        type="chart",
                        chart_spec=ChartSpec(
                            chart_type="bar",
                            categories=["Q1", "Q2"],
                            series=[
                                ChartSeries(name="Revenue", values=[12.0, 18.0]),
                            ],
                        ),
                    ),
                ],
            ),
        ],
        counters=Counters(slides=1, nodes=2),
    )

    registry = TemplateLayoutRegistry(manifest_path)
    reflow_deck(deck, registry)

    computed = deck.slides[0].computed["n-2"]
    assert computed.content_type == "chart"
    assert (computed.x, computed.y, computed.width, computed.height) == (
        540.0,
        170.0,
        420.0,
        320.0,
    )
