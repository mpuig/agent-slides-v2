"""Manifest-driven reflow for template-backed decks."""

from __future__ import annotations

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.slide_revisions import resolve_slide_revision
from agent_slides.engine.reflow import _normalize_deck_font_sizes, _resolve_text_ladder
from agent_slides.engine.text_fit import fit_text
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.layout_provider import TemplateLayoutRegistry
from agent_slides.model.themes import resolve_style
from agent_slides.model.types import ComputedNode, Deck


def template_reflow(
    deck: Deck,
    registry: TemplateLayoutRegistry,
    *,
    previous_slide_signatures: dict[str, object] | None = None,
) -> None:
    """Populate computed nodes from template placeholder bounds and theme."""

    theme = registry.theme
    design_rules = load_design_rules(deck.design_rules)
    for slide in deck.slides:
        slide_revision = resolve_slide_revision(
            slide,
            deck_revision=deck.revision,
            previous_slide_signatures=previous_slide_signatures,
        )
        layout_def = registry.get_layout(slide.layout)
        computed: dict[str, ComputedNode] = {}
        slide.revision = slide_revision

        for node in slide.nodes:
            if node.slot_binding is None:
                continue
            if node.slot_binding not in layout_def.slots:
                raise AgentSlidesError(
                    code=INVALID_SLOT,
                    message=f"Slot '{node.slot_binding}' is not defined for layout '{slide.layout}'.",
                )

            slot = layout_def.slots[node.slot_binding]
            if None in (slot.x, slot.y, slot.width, slot.height):
                raise AgentSlidesError(
                    code=INVALID_SLOT,
                    message=f"Slot '{node.slot_binding}' is missing bounds for layout '{slide.layout}'.",
                )

            x = float(slot.x)
            y = float(slot.y)
            width = float(slot.width)
            height = float(slot.height)
            style = resolve_style(theme, slot.role)

            if slot.role == "image" or node.type == "image":
                computed[node.node_id] = ComputedNode(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    font_size_pt=0.0,
                    font_family=str(style["font_family"]),
                    color=str(style["color"]),
                    bg_color=slot.bg_color if slot.bg_color is not None else theme.colors.background,
                    bg_transparency=slot.bg_transparency,
                    font_bold=bool(style["font_bold"]),
                    text_overflow=False,
                    revision=slide_revision,
                    content_type="image",
                    image_fit=str(node.style_overrides.get("image_fit", "contain")),
                )
                continue

            fit_rules = registry.get_text_fitting(slide.layout, slot.role)
            ladder = _resolve_text_ladder(fit_rules, slot.role, design_rules)
            font_size_pt, text_overflow = fit_text(
                text=node.content,
                width=width,
                height=height,
                default_size=fit_rules.default_size,
                min_size=fit_rules.min_size,
                role=slot.role,
                font_family=str(style["font_family"]),
                ladder=ladder,
            )
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=font_size_pt,
                font_family=str(style["font_family"]),
                color=str(style["color"]),
                bg_color=slot.bg_color if slot.bg_color is not None else theme.colors.background,
                bg_transparency=slot.bg_transparency,
                font_bold=bool(style["font_bold"]),
                text_overflow=text_overflow,
                revision=slide_revision,
                content_type="text",
            )

        slide.computed = computed

    _normalize_deck_font_sizes(deck, registry, design_rules)
