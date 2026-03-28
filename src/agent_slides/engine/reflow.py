"""Compute concrete slide geometry and resolved styling."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import isclose

from agent_slides.errors import AgentSlidesError, INVALID_SLOT
from agent_slides.engine.constraints import Rect, constraints_from_layout, solve
from agent_slides.engine.layout_validator import LayoutViolation, TEXT_OVERFLOW, validate_layout
from agent_slides.engine.slide_revisions import resolve_slide_revision
from agent_slides.icons import require_icon
from agent_slides.engine.text_fit import compose_blocks, fit_blocks, fit_text, measure_text_height
from agent_slides.engine.validator import validate_slide
from agent_slides.model import Deck, LayoutDef, Slide
from agent_slides.model.design_rules import DesignRules, load_design_rules
from agent_slides.model.layout_provider import BuiltinLayoutProvider, LayoutProvider
from agent_slides.model.layouts import DEFAULT_TEXT_FITTING
from agent_slides.model.themes import load_theme, resolve_style
from agent_slides.model.types import ComputedNode, Node, NodeContent, TextBlock, TextFitting, Theme


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
        slot = layout_def.slots[slot_name]
        fit_rules = _text_fit_rules(layout_def, node, provider)
        inner_width = max(width - (2 * slot.padding), 0.0)
        return measure_text_height(node.content, inner_width, fit_rules.default_size) + (2 * slot.padding)

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


def _block_text_fitting(layout_def: LayoutDef, provider: LayoutProvider, role: str) -> dict[str, TextFitting]:
    text_fitting = dict(layout_def.text_fitting)
    try:
        text_fitting[role] = provider.get_text_fitting(layout_def.name, role)
    except (AgentSlidesError, KeyError):
        text_fitting.setdefault(role, DEFAULT_TEXT_FITTING.get(role, DEFAULT_TEXT_FITTING["body"]))
    try:
        text_fitting["heading"] = provider.get_text_fitting(layout_def.name, "heading")
    except (AgentSlidesError, KeyError):
        text_fitting.setdefault("heading", DEFAULT_TEXT_FITTING["heading"])
    return text_fitting


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

@dataclass(frozen=True)
class _VariantTextAssignment:
    candidate_node_id: str
    slot_name: str
    source_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class _VariantCandidate:
    slide: Slide
    text_assignments: tuple[_VariantTextAssignment, ...]
    image_assignments: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _ReflowOutcome:
    rects: dict[str, Rect]
    violations: list[LayoutViolation]
    fallback_used: bool


def _slot_sort_key(layout_def: LayoutDef, slot_name: str) -> tuple[int, float, float, str]:
    slot = layout_def.slots[slot_name]
    return (
        slot.reading_order,
        float(slot.y if slot.y is not None else 0.0),
        float(slot.x if slot.x is not None else 0.0),
        slot_name,
    )


def _ordered_slot_names(layout_def: LayoutDef, *, role: str | None = None, include_image: bool = True) -> list[str]:
    slot_names = sorted(layout_def.slots, key=lambda slot_name: _slot_sort_key(layout_def, slot_name))
    if role is not None:
        return [slot_name for slot_name in slot_names if layout_def.slots[slot_name].role == role]
    if include_image:
        return slot_names
    return [slot_name for slot_name in slot_names if layout_def.slots[slot_name].role != "image"]


def _ordered_nodes(slide: Slide, layout_def: LayoutDef, *, node_type: str) -> list[Node]:
    slot_order = {slot_name: index for index, slot_name in enumerate(_ordered_slot_names(layout_def))}
    return sorted(
        [node for node in slide.nodes if node.type == node_type and node.slot_binding is not None],
        key=lambda node: (slot_order.get(node.slot_binding or "", len(slot_order)), node.node_id),
    )


def _chunk_nodes(nodes: list[Node], chunk_count: int) -> list[list[Node]]:
    if chunk_count <= 0 or not nodes:
        return []
    if len(nodes) <= chunk_count:
        return [[node] for node in nodes]

    chunks: list[list[Node]] = []
    cursor = 0
    remaining_nodes = len(nodes)
    remaining_chunks = chunk_count
    while remaining_chunks > 0 and cursor < len(nodes):
        size = max(1, remaining_nodes // remaining_chunks)
        if remaining_nodes % remaining_chunks:
            size += 1
        chunks.append(nodes[cursor : cursor + size])
        cursor += size
        remaining_nodes = len(nodes) - cursor
        remaining_chunks -= 1
    return chunks


def _clone_content(node: Node) -> NodeContent:
    if isinstance(node.content, NodeContent):
        return node.content
    return NodeContent.model_validate(node.content)


def _merged_content(nodes: Iterable[Node]) -> NodeContent:
    blocks: list[TextBlock] = []
    for node in nodes:
        blocks.extend(block.model_copy(deep=True) for block in _clone_content(node).blocks if block.text.strip())
    return NodeContent(blocks=blocks)


def _annotate_computed_metadata(
    computed: dict[str, ComputedNode],
    *,
    layout_used: str | None,
    fallback_reason: str | None,
    overflow_reason: str | None,
) -> None:
    for node in computed.values():
        node.layout_used = layout_used
        node.layout_fallback_reason = fallback_reason
        node.layout_overflow_reason = overflow_reason


def _slide_violations(layout_def: LayoutDef, slide: Slide, rects: dict[str, Rect]) -> list[LayoutViolation]:
    return validate_layout(layout_def, rects, computed_by_slot=_computed_by_slot(slide))


def _first_failure_reason(
    slide: Slide,
    violations: list[LayoutViolation],
    rules: DesignRules,
) -> str:
    for node in slide.nodes:
        if node.type != "text" or node.slot_binding is None:
            continue
        computed = slide.computed.get(node.node_id)
        if computed and computed.text_overflow:
            return f"text overflow in {node.slot_binding}"

    for violation in violations:
        if violation.code == TEXT_OVERFLOW and violation.slot_refs:
            return f"text overflow in {violation.slot_refs[0]}"

    for constraint in validate_slide(slide, rules):
        if constraint.severity == "error":
            return constraint.message.rstrip(".")

    if violations:
        return violations[0].message.rstrip(".")
    return "layout validation failed"


def _build_variant_candidate(
    slide: Slide,
    current_layout: LayoutDef,
    variant_layout: LayoutDef,
) -> _VariantCandidate | None:
    if any(node.type in {"chart", "table"} or node.slot_binding is None for node in slide.nodes):
        return None

    text_sources = _ordered_nodes(slide, current_layout, node_type="text")
    image_sources = _ordered_nodes(slide, current_layout, node_type="image")
    image_slots = _ordered_slot_names(variant_layout, role="image")
    if len(image_sources) > len(image_slots):
        return None

    heading_sources = [
        node for node in text_sources if current_layout.slots.get(node.slot_binding or "", None) and current_layout.slots[node.slot_binding].role == "heading"
    ]
    body_sources = [node for node in text_sources if node not in heading_sources]
    heading_slots = _ordered_slot_names(variant_layout, role="heading")
    body_slots = [
        slot_name
        for slot_name in _ordered_slot_names(variant_layout, include_image=False)
        if variant_layout.slots[slot_name].role != "heading"
    ]

    candidate_nodes: list[Node] = []
    text_assignments: list[_VariantTextAssignment] = []
    remaining_sources = list(body_sources)
    if heading_slots:
        if not heading_sources:
            return None
        source_node = heading_sources[0]
        candidate_node_id = "__fallback_heading"
        candidate_nodes.append(
            Node(
                node_id=candidate_node_id,
                slot_binding=heading_slots[0],
                type="text",
                content=_merged_content([source_node]),
            )
        )
        text_assignments.append(
            _VariantTextAssignment(
                candidate_node_id=candidate_node_id,
                slot_name=heading_slots[0],
                source_node_ids=(source_node.node_id,),
            )
        )
        remaining_sources = heading_sources[1:] + remaining_sources
    else:
        remaining_sources = heading_sources + remaining_sources

    for index, (slot_name, source_group) in enumerate(
        zip(body_slots, _chunk_nodes(remaining_sources, len(body_slots)), strict=False)
    ):
        if not source_group:
            continue
        candidate_node_id = f"__fallback_body_{index}"
        candidate_nodes.append(
            Node(
                node_id=candidate_node_id,
                slot_binding=slot_name,
                type="text",
                content=_merged_content(source_group),
            )
        )
        text_assignments.append(
            _VariantTextAssignment(
                candidate_node_id=candidate_node_id,
                slot_name=slot_name,
                source_node_ids=tuple(node.node_id for node in source_group),
            )
        )

    image_assignments: list[tuple[str, str]] = []
    for index, (slot_name, source_node) in enumerate(zip(image_slots, image_sources, strict=False)):
        candidate_node_id = f"__fallback_image_{index}"
        candidate_nodes.append(
            source_node.model_copy(
                update={
                    "node_id": candidate_node_id,
                    "slot_binding": slot_name,
                },
                deep=True,
            )
        )
        image_assignments.append((candidate_node_id, source_node.node_id))

    return _VariantCandidate(
        slide=Slide(
            slide_id=slide.slide_id,
            layout=variant_layout.name,
            nodes=candidate_nodes,
        ),
        text_assignments=tuple(text_assignments),
        image_assignments=tuple(image_assignments),
    )


def _map_candidate_to_original_computed(
    slide: Slide,
    candidate: _VariantCandidate,
    variant_layout: LayoutDef,
    provider: LayoutProvider,
    design_rules: DesignRules,
) -> dict[str, ComputedNode] | None:
    source_nodes = {node.node_id: node for node in slide.nodes}
    mapped: dict[str, ComputedNode] = {}

    for candidate_node_id, source_node_id in candidate.image_assignments:
        mapped[source_node_id] = candidate.slide.computed[candidate_node_id].model_copy(deep=True)

    for assignment in candidate.text_assignments:
        base = candidate.slide.computed[assignment.candidate_node_id]
        sources = [source_nodes[node_id] for node_id in assignment.source_node_ids]
        if len(sources) == 1:
            mapped[sources[0].node_id] = base.model_copy(deep=True)
            continue

        slot = variant_layout.slots[assignment.slot_name]
        slot_role = slot.role
        fit_rules = provider.get_text_fitting(variant_layout.name, slot_role)
        text_fitting = _block_text_fitting(variant_layout, provider, slot_role)
        ladder = _resolve_text_ladder(fit_rules, slot_role, design_rules)
        measured_heights = [
            max(
                1.0,
                measure_text_height(
                    _clone_content(source),
                    max(base.width - (2 * slot.padding), 0.0),
                    max(base.font_size_pt, 1.0),
                )
                + (2 * slot.padding),
            )
            for source in sources
        ]
        total_height = sum(measured_heights)
        scale = base.height / total_height if total_height > 0 else 1.0 / len(sources)
        y_cursor = base.y
        for index, source in enumerate(sources):
            height = (
                (base.y + base.height - y_cursor)
                if index == len(sources) - 1
                else measured_heights[index] * scale
            )
            font_size_pt, overflow = fit_text(
                text=_clone_content(source),
                width=base.width,
                height=height,
                default_size=fit_rules.default_size,
                min_size=fit_rules.min_size,
                role=slot_role,
                font_family=base.font_family,
                ladder=ladder,
            )
            if overflow:
                return None
            block_fits, block_overflow = fit_blocks(
                source.content.blocks,
                max(base.width - (2 * slot.padding), 0.0),
                max(height - (2 * slot.padding), 0.0),
                role=slot_role,
                text_fitting=text_fitting,
                spacing_rules=design_rules.block_spacing,
                type_ladders=design_rules.type_ladders,
                font_family=base.font_family,
                use_precise=False,
                fit_text_fn=fit_text,
            )
            if block_overflow:
                return None
            block_positions = compose_blocks(
                x=base.x,
                y=y_cursor,
                width=base.width,
                height=height,
                padding=slot.padding,
                vertical_align=slot.vertical_align,
                block_fits=block_fits,
                spacing_rules=design_rules.block_spacing,
            )
            mapped[source.node_id] = base.model_copy(
                update={
                    "y": y_cursor,
                    "height": height,
                    "font_size_pt": block_positions[0].font_size_pt if block_positions else font_size_pt,
                    "text_overflow": False,
                    "block_positions": block_positions,
                },
                deep=True,
            )
            mapped[source.node_id].font_size_pt = _slot_font_size(source, mapped[source.node_id])
            y_cursor += height

    bound_node_ids = {node.node_id for node in slide.nodes if node.slot_binding is not None}
    if set(mapped) != bound_node_ids:
        return None
    return mapped


def reflow_slide_with_fallback(
    slide: Slide,
    provider: LayoutProvider,
    theme: Theme,
    rules: DesignRules,
    *,
    revision: int,
) -> _ReflowOutcome:
    layout_def = provider.get_layout(slide.layout)

    primary_candidate = slide.model_copy(deep=True)
    primary_rects = _reflow_slide(
        primary_candidate,
        layout_def,
        theme,
        revision=revision,
        provider=provider,
        design_rules=rules,
    )
    primary_violations = _slide_violations(layout_def, primary_candidate, primary_rects)
    if not primary_violations:
        slide.revision = primary_candidate.revision
        slide.computed = primary_candidate.computed
        _annotate_computed_metadata(
            slide.computed,
            layout_used=None,
            fallback_reason=None,
            overflow_reason=None,
        )
        return _ReflowOutcome(rects=primary_rects, violations=[], fallback_used=False)

    if not any(violation.code == TEXT_OVERFLOW for violation in primary_violations):
        slide.revision = primary_candidate.revision
        slide.computed = primary_candidate.computed
        _annotate_computed_metadata(
            slide.computed,
            layout_used=None,
            fallback_reason=None,
            overflow_reason=None,
        )
        return _ReflowOutcome(rects=primary_rects, violations=primary_violations, fallback_used=False)

    failure_reason = _first_failure_reason(primary_candidate, primary_violations, rules)
    for variant_layout in provider.get_variants(slide.layout):
        candidate = _build_variant_candidate(slide, layout_def, variant_layout)
        if candidate is None:
            continue
        candidate_rects = _reflow_slide(
            candidate.slide,
            variant_layout,
            theme,
            revision=revision,
            provider=provider,
            design_rules=rules,
        )
        candidate_violations = _slide_violations(variant_layout, candidate.slide, candidate_rects)
        if candidate_violations:
            continue

        mapped = _map_candidate_to_original_computed(slide, candidate, variant_layout, provider, rules)
        if mapped is None:
            continue

        slide.revision = revision
        slide.computed = mapped
        _annotate_computed_metadata(
            slide.computed,
            layout_used=variant_layout.name,
            fallback_reason=failure_reason,
            overflow_reason=None,
        )
        return _ReflowOutcome(rects=candidate_rects, violations=[], fallback_used=True)

    slide.revision = primary_candidate.revision
    slide.computed = primary_candidate.computed
    _annotate_computed_metadata(
        slide.computed,
        layout_used=None,
        fallback_reason=None,
        overflow_reason=failure_reason,
    )
    return _ReflowOutcome(rects=primary_rects, violations=primary_violations, fallback_used=False)


def _slot_font_size(node: Node, computed: ComputedNode) -> float:
    if not computed.block_positions:
        return computed.font_size_pt

    positions_by_index = {position.block_index: position for position in computed.block_positions}
    for index, block in enumerate(node.content.blocks):
        if block.type != "heading" and index in positions_by_index:
            return positions_by_index[index].font_size_pt

    return computed.block_positions[0].font_size_pt


def _align_peer_baselines(nodes: list[ComputedNode]) -> None:
    positioned = [node for node in nodes if node.block_positions]
    if len(positioned) < 2:
        return

    baseline_y = max(node.block_positions[0].y for node in positioned)
    for node in positioned:
        offset = baseline_y - node.block_positions[0].y
        if offset <= 0:
            continue
        for position in node.block_positions:
            position.y += offset


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
    peer_groups: dict[str, list[ComputedNode]] = {}
    slide.revision = revision
    active_provider = provider or BuiltinLayoutProvider()
    active_design_rules = design_rules or load_design_rules("default")
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

        if node.type == "icon":
            computed[node.node_id] = ComputedNode(
                x=float(node.x or 0.0),
                y=float(node.y or 0.0),
                width=float(node.size or 0.0),
                height=float(node.size or 0.0),
                font_size_pt=0.0,
                font_family=theme.fonts.body,
                color=str(node.color or theme.colors.text),
                bg_color=None,
                bg_transparency=0.0,
                font_bold=False,
                text_overflow=False,
                revision=revision,
                content_type="icon",
                icon_svg_path=require_icon(str(node.icon_name)),
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
        text_fitting = _block_text_fitting(layout_def, active_provider, slot.role)
        block_fits, text_overflow = fit_blocks(
            node.content.blocks,
            max(width - (2 * slot.padding), 0.0),
            max(height - (2 * slot.padding), 0.0),
            role=slot.role,
            text_fitting=text_fitting,
            spacing_rules=active_design_rules.block_spacing,
            type_ladders=active_design_rules.type_ladders,
            font_family=str(style["font_family"]),
            use_precise=False,
            fit_text_fn=fit_text,
        )
        block_positions = compose_blocks(
            x=x,
            y=y,
            width=width,
            height=height,
            padding=slot.padding,
            vertical_align=slot.vertical_align,
            block_fits=block_fits,
            spacing_rules=active_design_rules.block_spacing,
        )
        computed_node = ComputedNode(
            x=x,
            y=y,
            width=width,
            height=height,
            font_size_pt=block_positions[0].font_size_pt if block_positions else 0.0,
            font_family=str(style["font_family"]),
            color=str(style["color"]),
            bg_color=slot.bg_color if slot.bg_color is not None else theme.colors.background,
            bg_transparency=slot.bg_transparency,
            font_bold=bool(style["font_bold"]),
            text_overflow=text_overflow,
            image_fit=node.image_fit,
            revision=revision,
            content_type="text",
            block_positions=block_positions,
        )
        computed_node.font_size_pt = _slot_font_size(node, computed_node)
        computed[node.node_id] = computed_node
        if slot.peer_group:
            peer_groups.setdefault(slot.peer_group, []).append(computed_node)

    for nodes in peer_groups.values():
        _align_peer_baselines(nodes)

    slide.computed = computed
    return rects


def reflow_slide(
    slide: Slide,
    layout_def: LayoutDef,
    theme: Theme,
    design_rules: DesignRules | None = None,
) -> list[LayoutViolation]:
    """Compute concrete geometry and styling for a single slide."""

    rects = _reflow_slide(slide, layout_def, theme, revision=0, design_rules=design_rules or load_design_rules("default"))
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
    outcomes_by_slide: dict[str, _ReflowOutcome] = {}
    for slide in deck.slides:
        slide_revision = resolve_slide_revision(
            slide,
            deck_revision=deck.revision,
            previous_slide_signatures=previous_slide_signatures,
        )
        outcomes_by_slide[slide.slide_id] = reflow_slide_with_fallback(
            slide,
            active_provider,
            theme,
            design_rules,
            revision=slide_revision,
        )
    _normalize_deck_font_sizes(deck, active_provider, design_rules)
    violations_by_slide: dict[str, list[LayoutViolation]] = {}
    for slide_id, outcome in outcomes_by_slide.items():
        if outcome.violations:
            violations_by_slide[slide_id] = outcome.violations
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
