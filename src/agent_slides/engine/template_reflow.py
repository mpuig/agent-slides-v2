"""Manifest-driven reflow for template-backed decks."""

from __future__ import annotations

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.text_fit import fit_text
from agent_slides.model.layout_provider import TemplateLayoutRegistry
from agent_slides.model.themes import resolve_style
from agent_slides.model.types import ComputedNode, Deck


def template_reflow(deck: Deck, registry: TemplateLayoutRegistry) -> None:
    """Populate computed nodes from template placeholder bounds and theme."""

    theme = registry.theme
    for slide in deck.slides:
        layout_def = registry.get_layout(slide.layout)
        computed: dict[str, ComputedNode] = {}

        for node in slide.nodes:
            if node.slot_binding is None:
                continue
            if node.slot_binding not in layout_def.slots:
                raise AgentSlidesError(
                    code=INVALID_SLOT,
                    message=f"Slot '{node.slot_binding}' is not defined for layout '{slide.layout}'.",
                )

            slot = layout_def.slots[node.slot_binding]
            placeholder = registry.get_placeholder(slide.layout, node.slot_binding)
            bounds = placeholder["bounds"]
            x = float(bounds["x"])
            y = float(bounds["y"])
            width = float(bounds["w"])
            height = float(bounds["h"])
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
                    bg_color=theme.colors.background,
                    bg_transparency=0.0,
                    font_bold=bool(style["font_bold"]),
                    text_overflow=False,
                    revision=deck.revision,
                    content_type="image",
                    image_fit=str(node.style_overrides.get("image_fit", "contain")),
                )
                continue

            fit_rules = registry.get_text_fitting(slide.layout, slot.role)
            font_size_pt, text_overflow = fit_text(
                text=node.content,
                width=width,
                height=height,
                default_size=fit_rules.default_size,
                min_size=fit_rules.min_size,
            )
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=font_size_pt,
                font_family=str(style["font_family"]),
                color=str(style["color"]),
                bg_color=theme.colors.background,
                bg_transparency=0.0,
                font_bold=bool(style["font_bold"]),
                text_overflow=text_overflow,
                revision=deck.revision,
                content_type="text",
            )

        slide.computed = computed
