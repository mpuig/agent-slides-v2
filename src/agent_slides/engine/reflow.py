"""Compute concrete slide geometry and resolved styling."""

from __future__ import annotations

from collections.abc import Callable
from math import isclose

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.constraints import Rect, constraints_from_layout, solve
from agent_slides.engine.layout_validator import LayoutViolation, validate_layout
from agent_slides.engine.slide_revisions import resolve_slide_revision
from agent_slides.engine.text_fit import fit_text, measure_text_height
from agent_slides.model import Deck, LayoutDef, Slide
from agent_slides.model.design_rules import DesignRules, load_design_rules
from agent_slides.model.layout_provider import BuiltinLayoutProvider, LayoutProvider
from agent_slides.model.layouts import DEFAULT_TEXT_FITTING
from agent_slides.model.themes import load_theme, resolve_style
from agent_slides.model.types import ComputedNode, Node, TextFitting, Theme


def _text_fit_rules(layout_def: LayoutDef, node: Node, provider: LayoutProvider | None = None) -> TextFitting:
    slot_name = node.slot_binding or ""
    slot = layout_def.slots[slot_name]
    if provider is not None:
        try:
            return provider.get_text_fitting(layout_def.name, slot.role)
        except AgentSlidesError:
            pass
    if slot.role in layout_def.text_fitting:
        return layout_def.text_fitting[slot.role]
    if slot.role == "heading":
        return DEFAULT_TEXT_FITTING["heading"]
    return DEFAULT_TEXT_FITTING["body"]


def _resolve_theme(deck: Deck, provider: LayoutProvider) -> Theme:
    return getattr(provider, "theme", None) or load_theme(deck.theme)


def _content_by_slot(slide: Slide) -> dict[str, Node]:
    return {
        node.slot_binding: node
        for node in slide.nodes
        if node.slot_binding is not None
    }


def _shape_dimension(node: Node, key: str) -> float:
    value = node.style_overrides[key]
    assert isinstance(value, int | float)
    return float(value)


def _shape_geometry(node: Node) -> tuple[float, float, float, float]:
    x = _shape_dimension(node, "x")
    y = _shape_dimension(node, "y")
    width = _shape_dimension(node, "width")
    height = _shape_dimension(node, "height")
    spec = node.shape_spec
    if spec is not None and spec.shape_type != "line":
        min_visible = max(12.0, spec.line_width * 6.0)
        if width == 0.0:
            width = min_visible
        if height == 0.0:
            height = min_visible
    return x, y, width, height


def _measure_slot_height_factory(layout_def: LayoutDef, provider: LayoutProvider) -> Callable[[str, object | None, float], float]:
    def measure(slot_name: str, content: object | None, width: float) -> float:
        node = content if isinstance(content, Node) else None
        if node is None:
            return 0.0
        fit_rules = _text_fit_rules(layout_def, node, provider)
        return measure_text_height(node.content, width, fit_rules.default_size)

    return measure


def _computed_by_slot(slide: Slide) -> dict[str, ComputedNode]:
    computed_by_slot: dict[str, ComputedNode] = {}
    for node in slide.nodes:
        if node.slot_binding is None:
            continue
        computed = slide.computed.get(node.node_id)
        if computed is not None:
            computed_by_slot[node.slot_binding] = computed
    return computed_by_slot


def _resolve_text_ladder(
    fit_rules: TextFitting,
    role: str,
    design_rules: DesignRules | None,
) -> list[float] | None:
    if fit_rules.ladder:
        return list(fit_rules.ladder)
    if design_rules is None:
        return None
    configured = design_rules.type_ladders.get(role, [])
    ladder = [size for size in configured if fit_rules.min_size <= size <= fit_rules.default_size]
    return ladder or None


def _normalize_deck_font_sizes(deck: Deck, provider: LayoutProvider, design_rules: DesignRules) -> None:
    if not design_rules.normalize_font_sizes:
        return

    role_minimums: dict[str, float] = {}
    entries: list[tuple[Node, ComputedNode, str, TextFitting, list[float] | None]] = []

    for slide in deck.slides:
        layout_def = provider.get_layout(slide.layout)
        for node in slide.nodes:
            if node.type != "text" or node.slot_binding is None:
                continue
            if node.node_id not in slide.computed:
                continue

            slot = layout_def.slots[node.slot_binding]
            if slot.role == "image":
                continue

            computed = slide.computed[node.node_id]
            fit_rules = provider.get_text_fitting(slide.layout, slot.role)
            ladder = _resolve_text_ladder(fit_rules, slot.role, design_rules)
            entries.append((node, computed, slot.role, fit_rules, ladder))
            current = role_minimums.get(slot.role)
            if current is None or computed.font_size_pt < current:
                role_minimums[slot.role] = computed.font_size_pt

    for node, computed, role, fit_rules, ladder in entries:
        target_size = role_minimums[role]
        if computed.font_size_pt <= target_size:
            continue
        if ladder is not None and not any(isclose(size, target_size, rel_tol=0.0, abs_tol=1e-6) for size in ladder):
            continue

        normalized_size, overflow = fit_text(
            text=node.content,
            width=computed.width,
            height=computed.height,
            default_size=fit_rules.default_size,
            min_size=fit_rules.min_size,
            role=role,
            font_family=computed.font_family,
            ladder=[target_size],
        )
        if overflow or not isclose(normalized_size, target_size, rel_tol=0.0, abs_tol=1e-6):
            continue
        computed.font_size_pt = normalized_size
        computed.text_overflow = False


def _reflow_slide(
    slide: Slide,
    layout_def: LayoutDef,
    theme: Theme,
    *,
    revision: int,
    provider: LayoutProvider | None = None,
    design_rules: DesignRules | None = None,
) -> dict[str, Rect]:
    computed: dict[str, ComputedNode] = {}
    slide.revision = revision
    active_provider = provider or BuiltinLayoutProvider()
    slot_constraints = constraints_from_layout(layout_def, theme)
    content_by_slot = _content_by_slot(slide)
    rects = solve(slot_constraints, content_by_slot, _measure_slot_height_factory(layout_def, active_provider))

    for node in slide.nodes:
        if node.type == "shape":
            x, y, width, height = _shape_geometry(node)
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=0.0,
                font_family="",
                color="#000000",
                bg_color=None,
                bg_transparency=0.0,
                font_bold=False,
                text_overflow=False,
                revision=revision,
                content_type="shape",
            )
            continue

        if node.slot_binding is None:
            continue
        if node.slot_binding not in layout_def.slots:
            raise AgentSlidesError(
                code=INVALID_SLOT,
                message=f"Slot '{node.slot_binding}' is not defined for layout '{layout_def.name}'.",
            )

        slot = layout_def.slots[node.slot_binding]
        rect = rects[node.slot_binding]
        x = rect.x
        y = rect.y
        width = rect.width
        height = rect.height
        if node.type in {"chart", "table"}:
            style = resolve_style(theme, slot.role)
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=0.0,
                font_family=str(style["font_family"]),
                color=str(style["color"]),
                bg_color=None,
                bg_transparency=0.0,
                font_bold=bool(style["font_bold"]),
                text_overflow=False,
                revision=revision,
                content_type=node.type,
            )
            continue

        if slot.role == "image" or node.type == "image":
            image_fit = "stretch" if slot.full_bleed and node.image_fit == "contain" else node.image_fit
            computed[node.node_id] = ComputedNode(
                x=x,
                y=y,
                width=width,
                height=height,
                font_size_pt=0.0,
                font_family=theme.fonts.body,
                color=theme.colors.text,
                bg_color=None,
                bg_transparency=0.0,
                font_bold=False,
                text_overflow=False,
                revision=revision,
                content_type="image",
                image_fit=image_fit,
            )
            continue

        style = resolve_style(theme, slot.role)
        fit_rules = _text_fit_rules(layout_def, node, active_provider)
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
            image_fit=node.image_fit,
            revision=revision,
            content_type="text",
        )

    slide.computed = computed
    return rects


def reflow_slide(slide: Slide, layout_def: LayoutDef, theme: Theme) -> list[LayoutViolation]:
    """Compute concrete geometry and styling for a single slide."""

    rects = _reflow_slide(slide, layout_def, theme, revision=0)
    return validate_layout(layout_def, rects, computed_by_slot=_computed_by_slot(slide))


def reflow_deck(
    deck: Deck,
    provider: LayoutProvider | None = None,
    *,
    previous_slide_signatures: dict[str, object] | None = None,
) -> dict[str, list[LayoutViolation]]:
    """Reflow every slide in the deck using the deck theme."""

    active_provider = provider or BuiltinLayoutProvider()
    theme = _resolve_theme(deck, active_provider)
    design_rules = load_design_rules(deck.design_rules)
    rects_by_slide: dict[str, dict[str, Rect]] = {}
    for slide in deck.slides:
        layout_def = active_provider.get_layout(slide.layout)
        slide_revision = resolve_slide_revision(
            slide,
            deck_revision=deck.revision,
            previous_slide_signatures=previous_slide_signatures,
        )
        rects_by_slide[slide.slide_id] = _reflow_slide(
            slide,
            layout_def,
            theme,
            revision=slide_revision,
            provider=active_provider,
            design_rules=design_rules,
        )
    _normalize_deck_font_sizes(deck, active_provider, design_rules)
    violations_by_slide: dict[str, list[LayoutViolation]] = {}
    for slide in deck.slides:
        layout_def = active_provider.get_layout(slide.layout)
        violations = validate_layout(
            layout_def,
            rects_by_slide[slide.slide_id],
            computed_by_slot=_computed_by_slot(slide),
        )
        if violations:
            violations_by_slide[slide.slide_id] = violations
    return violations_by_slide


def rebind_slots(
    deck: Deck,
    slide: Slide,
    new_layout: LayoutDef | str,
    provider: LayoutProvider | None = None,
) -> list[str]:
    """Keep compatible slot bindings and create missing nodes for a new layout."""

    if isinstance(new_layout, str):
        if provider is None:
            raise TypeError("provider is required when rebinding by layout name")
        layout_getter = provider.get_layout
        new_layout = layout_getter(new_layout)
    desired_slots = tuple(new_layout.slots)
    claimed_slots: set[str] = set()
    unbound_node_ids: list[str] = []

    for node in slide.nodes:
        slot_name = node.slot_binding
        if slot_name is None:
            continue
        if slot_name in new_layout.slots and slot_name not in claimed_slots:
            claimed_slots.add(slot_name)
            continue
        unbound_node_ids.append(node.node_id)
        node.slot_binding = None

    for slot_name in desired_slots:
        if slot_name in claimed_slots:
            continue
        slot = new_layout.slots[slot_name]
        slide.nodes.append(
            Node(
                node_id=deck.next_node_id(),
                slot_binding=slot_name,
                type="image" if slot.role == "image" else "text",
                style_overrides={"placeholder": True} if slot.role == "image" else {},
            )
        )

    slide.layout = new_layout.name
    return unbound_node_ids
