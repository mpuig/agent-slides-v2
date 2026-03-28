"""Visual review helpers for rendered deck QA."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from agent_slides.engine.reflow import reflow_deck
from agent_slides.engine.template_reflow import template_reflow
from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io import mutate_deck, read_deck, resolve_manifest_path, write_computed_deck, write_pptx
from agent_slides.model import Deck, Node, NodeContent, Slide
from agent_slides.model.layout_provider import LayoutProvider, TemplateLayoutRegistry, resolve_layout_provider
from agent_slides.model.types import STANDARD_SLIDE_HEIGHT_PT, STANDARD_SLIDE_WIDTH_PT, TextBlock

CHECKLIST: dict[str, list[dict[str, str]]] = {
    "Visual Hierarchy": [
        {"key": "title_dominates", "label": "Title visually dominates"},
        {"key": "reading_order", "label": "Clear reading order"},
        {"key": "one_focal_point", "label": "One focal point per slide"},
        {"key": "intentional_whitespace", "label": "White space is intentional"},
        {"key": "squint_test", "label": "Squint test still preserves hierarchy"},
        {"key": "margins_respected", "label": "Content respects slide margins"},
    ],
    "Typography": [
        {"key": "heading_size_range", "label": "Heading font size is 24-44pt"},
        {"key": "body_size_range", "label": "Body font size is 10-18pt"},
        {"key": "font_size_consistency", "label": "Font sizes are consistent across the deck"},
        {"key": "font_family_limit", "label": "No more than 2 font families are used"},
        {"key": "bold_sparing", "label": "Bold is used sparingly"},
        {"key": "no_visible_overflow", "label": "Text is not visibly truncated or overflowing"},
    ],
    "Layout Quality": [
        {"key": "layout_matches_content", "label": "Layout matches the content relationship"},
        {"key": "columns_balanced", "label": "Columns are balanced"},
        {"key": "charts_within_bounds", "label": "Charts stay within slot bounds"},
        {"key": "content_density", "label": "Content areas are not excessively empty"},
        {"key": "grid_alignment", "label": "Grid alignment is consistent"},
        {"key": "image_slots_intentional", "label": "Image slots are filled or intentionally empty"},
    ],
    "Content Quality": [
        {"key": "action_title", "label": "Title is an action title"},
        {"key": "not_topic_label", "label": "Title is not a topic label"},
        {"key": "body_proves_title", "label": "Body content proves the title claim"},
        {"key": "bullet_limit", "label": "Slide stays within 6 bullets"},
        {"key": "bullet_concise", "label": "Bullets are concise"},
        {"key": "source_present", "label": "Slides with data claims include a source"},
        {"key": "chart_labeled", "label": "Charts have titles and clear labels"},
        {"key": "numbers_rounded", "label": "Numbers are rounded and readable"},
    ],
    "Deck-Level Patterns": [
        {"key": "layout_variety", "label": "Deck uses layout variety"},
        {"key": "no_three_repeat", "label": "Deck avoids 3+ consecutive duplicate layouts"},
        {"key": "title_slide_present", "label": "Title slide is present"},
        {"key": "closing_slide_present", "label": "Closing slide is present"},
        {"key": "visual_rhythm", "label": "Deck has visual rhythm across content types"},
        {"key": "theme_consistent", "label": "Theme stays visually consistent"},
    ],
    "AI Slop Detection": [
        {"key": "not_same_layout_everywhere", "label": "Not every slide uses the same layout"},
        {"key": "no_generic_titles", "label": "Titles avoid generic labels"},
        {"key": "not_bullet_wall_deck", "label": "Deck avoids bullet-wall repetition"},
        {"key": "no_empty_visual_slots", "label": "No empty image or chart slots remain"},
        {"key": "title_capitalization_consistent", "label": "Title capitalization is consistent"},
        {"key": "not_auto_generated", "label": "Content avoids auto-generated repetition"},
    ],
}

ITEM_METADATA: dict[str, dict[str, object]] = {
    "title_dominates": {"recommendation": "Increase title contrast or reduce competing text emphasis.", "severity": 4},
    "reading_order": {"recommendation": "Pull the main title upward and simplify left-to-right scanning.", "severity": 3},
    "one_focal_point": {"recommendation": "Remove or downweight secondary focal elements.", "severity": 3},
    "intentional_whitespace": {"recommendation": "Rebalance density so the slide neither feels cramped nor vacant.", "severity": 2},
    "squint_test": {"recommendation": "Strengthen the size or contrast difference between title and body.", "severity": 3},
    "margins_respected": {"recommendation": "Bring content back inside the layout margin.", "severity": 4},
    "heading_size_range": {"recommendation": "Keep headings within a 24-44pt working range.", "severity": 3},
    "body_size_range": {"recommendation": "Keep body copy within a 10-18pt readable range.", "severity": 4},
    "font_size_consistency": {"recommendation": "Normalize type sizes for the same role across slides.", "severity": 2},
    "font_family_limit": {"recommendation": "Reduce typography to at most two font families.", "severity": 2},
    "bold_sparing": {"recommendation": "Reserve bold for headings or the smallest possible emphasis set.", "severity": 2},
    "no_visible_overflow": {"recommendation": "Edit or split content until visible overflow disappears.", "severity": 5},
    "layout_matches_content": {"recommendation": "Choose a layout whose structure matches the relationship in the content.", "severity": 4},
    "columns_balanced": {"recommendation": "Balance content density across parallel columns.", "severity": 3},
    "charts_within_bounds": {"recommendation": "Give charts more space or reduce nearby text.", "severity": 4},
    "content_density": {"recommendation": "Use the content area more intentionally or simplify the layout.", "severity": 2},
    "grid_alignment": {"recommendation": "Realign elements to consistent column and row anchors.", "severity": 2},
    "image_slots_intentional": {"recommendation": "Fill image slots or switch to a non-image layout.", "severity": 3},
    "action_title": {"recommendation": "Rewrite the title as a takeaway sentence with a clear so-what.", "severity": 5},
    "not_topic_label": {"recommendation": "Replace the topic label with a conclusion-oriented title.", "severity": 5},
    "body_proves_title": {"recommendation": "Add evidence that directly supports the headline claim.", "severity": 4},
    "bullet_limit": {"recommendation": "Split or condense bullets to stay within six points.", "severity": 4},
    "bullet_concise": {"recommendation": "Shorten bullets to crisp fragments instead of paragraphs.", "severity": 3},
    "source_present": {"recommendation": "Add a source line for quantified or chart-driven claims.", "severity": 4},
    "chart_labeled": {"recommendation": "Add a chart title and make labels explicit.", "severity": 4},
    "numbers_rounded": {"recommendation": "Round large values to readable units and cut excess precision.", "severity": 2},
    "layout_variety": {"recommendation": "Introduce a second layout to avoid monotony.", "severity": 3},
    "no_three_repeat": {"recommendation": "Break up runs of identical layouts.", "severity": 2},
    "title_slide_present": {"recommendation": "Add a title slide that frames the story.", "severity": 4},
    "closing_slide_present": {"recommendation": "Add a closing slide with the takeaway or call to action.", "severity": 4},
    "visual_rhythm": {"recommendation": "Vary the mix of text, chart, and image-led slides.", "severity": 3},
    "theme_consistent": {"recommendation": "Keep type and color treatments aligned across the deck.", "severity": 2},
    "not_same_layout_everywhere": {"recommendation": "Avoid using the same layout on every slide.", "severity": 3},
    "no_generic_titles": {"recommendation": "Replace generic labels with slide-specific conclusions.", "severity": 5},
    "not_bullet_wall_deck": {"recommendation": "Introduce visuals or alternate structures to break up bullet walls.", "severity": 4},
    "no_empty_visual_slots": {"recommendation": "Remove or fill empty visual placeholders.", "severity": 3},
    "title_capitalization_consistent": {"recommendation": "Normalize title capitalization across the deck.", "severity": 1},
    "not_auto_generated": {"recommendation": "Reduce repetitive title and slide structures so the story feels authored.", "severity": 3},
}

GENERIC_TITLE_PATTERNS = (
    "introduction",
    "overview",
    "summary",
    "conclusion",
    "appendix",
    "market overview",
    "market analysis",
    "analysis",
    "background",
    "next steps",
    "recommendation",
    "approach",
    "results",
    "findings",
)
ACTION_VERBS = {
    "accelerates",
    "boosts",
    "cuts",
    "declines",
    "drives",
    "expands",
    "falls",
    "grew",
    "grows",
    "improves",
    "increases",
    "is",
    "lifts",
    "reduces",
    "remains",
    "shows",
    "slows",
    "unlocks",
    "wins",
}
RAW_NUMBER_PATTERN = re.compile(r"(?<![\d,])\d{5,}(?:\.\d+)?(?![\d,])")


@dataclass
class SlideContext:
    slide: Slide
    slide_index: int
    layout_slots: dict[str, Any]
    title_node: Node | None
    text_nodes: list[Node]
    body_nodes: list[Node]
    chart_nodes: list[Node]
    image_nodes: list[Node]
    screenshot_path: Path


def _grade_from_ratio(ratio: float) -> str:
    if ratio >= 0.97:
        return "A+"
    if ratio >= 0.93:
        return "A"
    if ratio >= 0.90:
        return "A-"
    if ratio >= 0.87:
        return "B+"
    if ratio >= 0.83:
        return "B"
    if ratio >= 0.80:
        return "B-"
    if ratio >= 0.77:
        return "C+"
    if ratio >= 0.73:
        return "C"
    if ratio >= 0.70:
        return "C-"
    if ratio >= 0.67:
        return "D+"
    if ratio >= 0.63:
        return "D"
    if ratio >= 0.60:
        return "D-"
    return "F"


def _relative_path(path: Path, base: Path) -> str:
    return str(path.resolve().relative_to(base.resolve()))


def _build_deck_artifact(deck_path: Path, pptx_path: Path) -> tuple[Deck, LayoutProvider]:
    deck = read_deck(str(deck_path))
    manifest_path = resolve_manifest_path(str(deck_path), deck)
    if manifest_path is not None:
        deck.template_manifest = manifest_path
    provider = resolve_layout_provider(manifest_path)
    if isinstance(provider, TemplateLayoutRegistry):
        template_reflow(deck, provider)
    else:
        reflow_deck(deck, provider)
    write_computed_deck(str(deck_path), deck)
    write_pptx(deck, str(pptx_path), asset_base_dir=deck_path.parent)
    return deck, provider


def _require_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise AgentSlidesError(SCHEMA_ERROR, f"Visual review requires '{name}' to be installed and available on PATH.")
    return resolved


def _run_process(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, cwd=cwd)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "external tool failed"
        raise AgentSlidesError(SCHEMA_ERROR, f"Visual review command failed: {message}") from exc


def render_pptx_to_pngs(pptx_path: Path, output_dir: Path, *, dpi: int) -> tuple[Path, list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdf"
    png_dir = output_dir / "slides"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    soffice = _require_command("soffice")
    pdftoppm = _require_command("pdftoppm")

    _run_process([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dir), str(pptx_path)])
    pdf_path = pdf_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        raise AgentSlidesError(SCHEMA_ERROR, f"LibreOffice did not produce the expected PDF: {pdf_path}")

    prefix = png_dir / "slide"
    _run_process([pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(prefix)])

    rendered = sorted(png_dir.glob("slide-*.png"))
    if not rendered:
        raise AgentSlidesError(SCHEMA_ERROR, "pdftoppm did not produce any slide PNGs.")

    normalized_paths: list[Path] = []
    for index, rendered_path in enumerate(rendered, start=1):
        normalized = png_dir / f"slide-{index:02d}.png"
        if normalized != rendered_path:
            rendered_path.replace(normalized)
        normalized_paths.append(normalized)

    return pdf_path, normalized_paths


def _node_text(node: Node) -> str:
    return node.content.to_plain_text().strip()


def _node_blocks(node: Node) -> list[TextBlock]:
    return list(node.content.blocks)


def _body_blocks(nodes: list[Node]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for node in nodes:
        blocks.extend(node.content.blocks)
    return blocks


def _role_for_node(node: Node, slots: dict[str, Any]) -> str | None:
    if node.slot_binding is None:
        return None
    slot_def = slots.get(node.slot_binding)
    return None if slot_def is None else str(slot_def.role)


def _computed(slide: Slide, node: Node) -> Any | None:
    return slide.computed.get(node.node_id)


def _title_case_style(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty"
    if stripped.isupper():
        return "upper"
    words = [word for word in re.split(r"\s+", stripped) if word]
    title_like = sum(1 for word in words if word[:1].isupper()) >= max(1, len(words) - 1)
    if title_like:
        return "title"
    if stripped[:1].isupper():
        return "sentence"
    return "mixed"


def _is_generic_title(title: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", "", title.casefold()).strip()
    if not normalized:
        return True
    if normalized in GENERIC_TITLE_PATTERNS:
        return True
    if any(normalized.endswith(pattern) for pattern in ("overview", "analysis", "summary", "introduction")):
        return True
    words = normalized.split()
    if len(words) <= 3 and not any(word in ACTION_VERBS for word in words):
        return True
    return False


def _looks_action_title(title: str) -> bool:
    normalized_words = set(re.findall(r"[a-z]+", title.casefold()))
    return not _is_generic_title(title) and bool(normalized_words & ACTION_VERBS)


def _word_count(text: str) -> int:
    return len([word for word in re.split(r"\s+", text.strip()) if word])


def _has_source_line(nodes: list[Node]) -> bool:
    for node in nodes:
        text = _node_text(node).casefold()
        if text.startswith("source:") or text.startswith("sources:"):
            return True
    return False


def _has_numeric_claim(context: SlideContext) -> bool:
    if context.chart_nodes:
        return True
    return any(re.search(r"\d", _node_text(node)) for node in context.text_nodes)


def _all_font_families(deck: Deck) -> set[str]:
    families: set[str] = set()
    for slide in deck.slides:
        for computed in slide.computed.values():
            family = computed.font_family.strip()
            if family:
                families.add(family)
    return families


def _find_title_node(slide: Slide, slots: dict[str, Any]) -> Node | None:
    headings = [node for node in slide.nodes if _role_for_node(node, slots) == "heading" and _node_text(node)]
    if headings:
        return headings[0]

    text_nodes = [node for node in slide.nodes if node.type == "text" and _node_text(node)]
    if not text_nodes:
        return None
    return max(
        text_nodes,
        key=lambda node: (
            (_computed(slide, node).font_size_pt if _computed(slide, node) else 0.0),
            -(_computed(slide, node).y if _computed(slide, node) else 0.0),
        ),
    )


def _make_slide_contexts(deck: Deck, provider: LayoutProvider, screenshots: list[Path]) -> list[SlideContext]:
    contexts: list[SlideContext] = []
    for index, slide in enumerate(deck.slides):
        slots = provider.get_layout(slide.layout).slots
        text_nodes = [node for node in slide.nodes if node.type == "text" and _node_text(node)]
        body_nodes = [node for node in text_nodes if _role_for_node(node, slots) in {"body", "quote", "attribution"}]
        chart_nodes = [node for node in slide.nodes if node.type == "chart"]
        image_nodes = [node for node in slide.nodes if node.type == "image"]
        contexts.append(
            SlideContext(
                slide=slide,
                slide_index=index,
                layout_slots=slots,
                title_node=_find_title_node(slide, slots),
                text_nodes=text_nodes,
                body_nodes=body_nodes,
                chart_nodes=chart_nodes,
                image_nodes=image_nodes,
                screenshot_path=screenshots[index],
            )
        )
    return contexts


def _occupancy_ratio(context: SlideContext) -> float:
    occupied_area = 0.0
    for node in context.slide.nodes:
        computed = _computed(context.slide, node)
        if computed is None:
            continue
        occupied_area += min(computed.width * computed.height, STANDARD_SLIDE_WIDTH_PT * STANDARD_SLIDE_HEIGHT_PT)
    slide_area = STANDARD_SLIDE_WIDTH_PT * STANDARD_SLIDE_HEIGHT_PT
    return min(occupied_area / slide_area, 1.0)


def _bounds_inside_margin(context: SlideContext, *, margin: float = 24.0) -> bool:
    for node in context.slide.nodes:
        computed = _computed(context.slide, node)
        if computed is None:
            continue
        if computed.x < margin or computed.y < margin:
            return False
        if computed.x + computed.width > STANDARD_SLIDE_WIDTH_PT - margin:
            return False
        if computed.y + computed.height > STANDARD_SLIDE_HEIGHT_PT - margin:
            return False
    return True


def _overlaps(a: Any, b: Any) -> bool:
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )


def _body_word_counts(context: SlideContext) -> list[int]:
    counts: list[int] = []
    for slot_name, slot_def in context.layout_slots.items():
        if str(slot_def.role) not in {"body", "quote"}:
            continue
        text = " ".join(_node_text(node) for node in context.slide.nodes if node.slot_binding == slot_name).strip()
        if text:
            counts.append(_word_count(text))
    return counts


def _numbers_readable(context: SlideContext) -> bool:
    for node in context.text_nodes:
        if RAW_NUMBER_PATTERN.search(_node_text(node)):
            return False
    for node in context.chart_nodes:
        chart = node.chart_spec
        if chart is None:
            continue
        series = chart.series or []
        for entry in series:
            for value in entry.values:
                if abs(value) >= 10000 and value == int(value):
                    return False
                if isinstance(value, float) and len(f"{value}".split(".")[-1]) > 2:
                    return False
    return True


def _default_chart_title(context: SlideContext, chart_node: Node) -> str:
    heading = _node_text(context.title_node) if context.title_node is not None else ""
    if heading:
        return heading
    chart = chart_node.chart_spec
    if chart is not None and chart.series:
        return chart.series[0].name
    return "Chart"


def _trend_title(chart_node: Node) -> str | None:
    chart = chart_node.chart_spec
    if chart is None or not chart.series:
        return None
    series = chart.series[0]
    if len(series.values) < 2:
        return None
    first_value = series.values[0]
    last_value = series.values[-1]
    if chart.categories and len(chart.categories) >= 2:
        start_label = chart.categories[0]
        end_label = chart.categories[-1]
    else:
        start_label = "the start"
        end_label = "the latest period"
    if first_value == 0:
        return None
    delta_ratio = (last_value - first_value) / abs(first_value)
    if abs(delta_ratio) < 0.03:
        verb = "held steady"
        return f"{series.name} held steady from {start_label} to {end_label}"
    verb = "increased" if delta_ratio > 0 else "declined"
    return f"{series.name} {verb} from {start_label} to {end_label}"


def _title_rewrite(context: SlideContext) -> str | None:
    if context.title_node is None:
        return None
    current = _node_text(context.title_node)
    if not _is_generic_title(current):
        return None

    for block in _body_blocks(context.body_nodes):
        candidate = block.text.strip().rstrip(".")
        if 5 <= _word_count(candidate) <= 14:
            return candidate[:120]

    for chart_node in context.chart_nodes:
        candidate = _trend_title(chart_node)
        if candidate:
            return candidate

    return None


def _slide_checks(context: SlideContext, *, median_heading_size: float, median_body_size: float, deck_families: set[str]) -> dict[str, tuple[bool, str]]:
    checks: dict[str, tuple[bool, str]] = {}
    title_node = context.title_node
    title_text = _node_text(title_node) if title_node is not None else ""
    title_computed = _computed(context.slide, title_node) if title_node is not None else None
    title_font_size = title_computed.font_size_pt if title_computed is not None else 0.0
    body_sizes = [
        computed.font_size_pt
        for node in context.body_nodes
        if (computed := _computed(context.slide, node)) is not None
    ]
    non_title_sizes = [
        computed.font_size_pt
        for node in context.text_nodes
        if node is not title_node and (computed := _computed(context.slide, node)) is not None
    ]
    ratio = _occupancy_ratio(context)
    bullet_blocks = [block for block in _body_blocks(context.body_nodes) if block.type == "bullet"]
    body_text = " ".join(_node_text(node) for node in context.body_nodes).strip()
    bold_body_nodes = [
        node
        for node in context.body_nodes
        if (computed := _computed(context.slide, node)) is not None and computed.font_bold
    ]
    slide_families = {
        computed.font_family.strip()
        for computed in context.slide.computed.values()
        if computed.font_family.strip()
    }

    title_order_ok = True
    if title_computed is not None:
        for node in context.slide.nodes:
            computed = _computed(context.slide, node)
            if computed is None or node is title_node:
                continue
            if computed.y + 4 < title_computed.y:
                title_order_ok = False
                break

    prominent_nodes = 0
    for node in context.slide.nodes:
        computed = _computed(context.slide, node)
        if computed is None:
            continue
        large_text = computed.font_size_pt >= max(title_font_size - 2.0, 20.0)
        large_area = computed.width * computed.height > (STANDARD_SLIDE_WIDTH_PT * STANDARD_SLIDE_HEIGHT_PT * 0.22)
        if large_text or large_area:
            prominent_nodes += 1

    checks["title_dominates"] = (
        title_node is not None and (not non_title_sizes or title_font_size >= max(non_title_sizes) + 4.0),
        f"title={title_font_size:.1f}pt",
    )
    checks["reading_order"] = (title_order_ok, "title appears first in the visual scan")
    checks["one_focal_point"] = (prominent_nodes <= 2, f"{prominent_nodes} prominent elements detected")
    checks["intentional_whitespace"] = (0.08 <= ratio <= 0.78, f"occupancy ratio {ratio:.2f}")
    checks["squint_test"] = (
        title_node is not None and (title_font_size >= max(non_title_sizes or [0.0]) * 1.2 or bool(context.chart_nodes or context.image_nodes)),
        "title contrast or single visual focus remains visible",
    )
    checks["margins_respected"] = (_bounds_inside_margin(context), "all computed bounds stay inside margins")

    checks["heading_size_range"] = (24.0 <= title_font_size <= 44.0, f"heading size {title_font_size:.1f}pt")
    checks["body_size_range"] = (all(10.0 <= size <= 18.0 for size in body_sizes), f"body sizes {body_sizes or ['n/a']}")
    checks["font_size_consistency"] = (
        abs(title_font_size - median_heading_size) <= 4.0 and all(abs(size - median_body_size) <= 3.0 for size in body_sizes or [median_body_size]),
        f"heading median {median_heading_size:.1f}pt, body median {median_body_size:.1f}pt",
    )
    checks["font_family_limit"] = (len(deck_families) <= 2 and len(slide_families) <= 2, f"deck families={sorted(deck_families)}")
    checks["bold_sparing"] = (len(bold_body_nodes) <= 1, f"{len(bold_body_nodes)} bold body nodes")
    checks["no_visible_overflow"] = (
        not any(computed.text_overflow for computed in context.slide.computed.values()),
        "no computed text overflow",
    )

    body_counts = _body_word_counts(context)
    column_balance = True
    if len(body_counts) >= 2 and max(body_counts) > 0:
        column_balance = min(body_counts) / max(body_counts) >= 0.4
    layout_ok = True
    if context.slide.layout in {"two_col", "comparison", "three_col"}:
        filled_body_slots = [count for count in body_counts if count > 0]
        layout_ok = len(filled_body_slots) >= 2
    if context.slide.layout in {"image_left", "image_right", "gallery", "hero_image"} and not any(
        node.image_path and not node.style_overrides.get("placeholder") for node in context.image_nodes
    ):
        layout_ok = False

    chart_overlap_ok = True
    chart_bounds: list[Any] = []
    other_bounds: list[Any] = []
    for node in context.slide.nodes:
        computed = _computed(context.slide, node)
        if computed is None:
            continue
        if node.type == "chart":
            chart_bounds.append(computed)
        else:
            other_bounds.append(computed)
    for chart_bound in chart_bounds:
        if any(_overlaps(chart_bound, other) for other in other_bounds):
            chart_overlap_ok = False
            break

    image_slot_ok = True
    image_slot_names = [slot_name for slot_name, slot_def in context.layout_slots.items() if str(slot_def.role) == "image"]
    for slot_name in image_slot_names:
        slot_images = [node for node in context.image_nodes if node.slot_binding == slot_name]
        if not slot_images:
            image_slot_ok = False
            break
        if all(not node.image_path and not node.style_overrides.get("placeholder") for node in slot_images):
            image_slot_ok = False
            break

    x_positions = sorted(
        round(_computed(context.slide, node).x, 1)
        for node in context.slide.nodes
        if _computed(context.slide, node) is not None
    )
    alignment_ok = len(set(x_positions)) <= max(3, len(context.layout_slots))

    checks["layout_matches_content"] = (layout_ok, f"layout={context.slide.layout}")
    checks["columns_balanced"] = (column_balance, f"column word counts={body_counts or ['n/a']}")
    checks["charts_within_bounds"] = (chart_overlap_ok, "charts do not overlap neighboring nodes")
    checks["content_density"] = (ratio >= 0.12 or len(context.slide.nodes) <= 1, f"occupancy ratio {ratio:.2f}")
    checks["grid_alignment"] = (alignment_ok, f"x anchors={x_positions}")
    checks["image_slots_intentional"] = (image_slot_ok, f"image slots={image_slot_names or ['none']}")

    chart_labeled = True
    for chart_node in context.chart_nodes:
        chart = chart_node.chart_spec
        if chart is None or not chart.title:
            chart_labeled = False
            break
        if chart.chart_type == "scatter":
            if not chart.scatter_series or any(not series.name for series in chart.scatter_series):
                chart_labeled = False
                break
        else:
            if not chart.categories or not chart.series or any(not series.name for series in chart.series):
                chart_labeled = False
                break

    checks["action_title"] = (_looks_action_title(title_text), title_text or "missing title")
    checks["not_topic_label"] = (not _is_generic_title(title_text), title_text or "missing title")
    checks["body_proves_title"] = (
        bool(body_text or context.chart_nodes or context.image_nodes),
        f"body words={_word_count(body_text)} chart_count={len(context.chart_nodes)}",
    )
    checks["bullet_limit"] = (len(bullet_blocks) <= 6, f"{len(bullet_blocks)} bullets")
    checks["bullet_concise"] = (
        all(_word_count(block.text) <= 18 for block in bullet_blocks),
        "all bullets stay within 18 words",
    )
    checks["source_present"] = (
        (not _has_numeric_claim(context)) or _has_source_line(context.text_nodes),
        "source line required for quantified claims",
    )
    checks["chart_labeled"] = (chart_labeled, f"{len(context.chart_nodes)} chart nodes")
    checks["numbers_rounded"] = (_numbers_readable(context), "no unreadable raw numbers detected")

    return checks


def _aggregate_item_status(slide_results: list[dict[str, tuple[bool, str]]], item_key: str) -> tuple[bool, int]:
    failures = sum(1 for result in slide_results if item_key in result and not result[item_key][0])
    return failures == 0, failures


def _deck_level_checks(contexts: list[SlideContext], deck: Deck) -> dict[str, tuple[bool, str, int | None]]:
    layouts = [context.slide.layout for context in contexts]
    unique_layouts = set(layouts)
    max_run = 1
    run = 1
    for left, right in zip(layouts, layouts[1:]):
        if left == right:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1

    has_title_slide = any(slide.layout == "title" for slide in deck.slides)
    has_closing_slide = any(slide.layout == "closing" for slide in deck.slides)
    content_kinds = set()
    generic_title_failures = 0
    bullet_wall_slides = 0
    empty_visual_slot_failures = 0
    title_styles = Counter()

    title_texts: list[str] = []
    for context in contexts:
        if context.chart_nodes:
            content_kinds.add("chart")
        if any(node.image_path for node in context.image_nodes):
            content_kinds.add("image")
        if context.body_nodes:
            content_kinds.add("text")

        title_text = _node_text(context.title_node) if context.title_node is not None else ""
        if title_text:
            title_texts.append(title_text.casefold())
            title_styles[_title_case_style(title_text)] += 1
        if _is_generic_title(title_text):
            generic_title_failures += 1
        bullet_count = len([block for block in _body_blocks(context.body_nodes) if block.type == "bullet"])
        if bullet_count >= 5:
            bullet_wall_slides += 1
        if not _slide_checks(
            context,
            median_heading_size=median(
                [
                    (_computed(item.slide, item.title_node).font_size_pt)
                    for item in contexts
                    if item.title_node is not None and _computed(item.slide, item.title_node) is not None
                ]
                or [32.0]
            ),
            median_body_size=median(
                [
                    _computed(item.slide, node).font_size_pt
                    for item in contexts
                    for node in item.body_nodes
                    if _computed(item.slide, node) is not None
                ]
                or [18.0]
            ),
            deck_families=_all_font_families(deck),
        )["image_slots_intentional"][0]:
            empty_visual_slot_failures += 1

    repeated_titles = Counter(title_texts)
    repetitive_titles = sum(1 for count in repeated_titles.values() if count >= 2)
    theme_consistent = len(_all_font_families(deck)) <= 2

    return {
        "layout_variety": (len(deck.slides) < 6 or len(unique_layouts) >= 2, f"{len(unique_layouts)} unique layouts", None),
        "no_three_repeat": (max_run < 3, f"longest identical layout run={max_run}", None),
        "title_slide_present": (has_title_slide, "deck includes a title slide", 0 if not has_title_slide and contexts else None),
        "closing_slide_present": (
            has_closing_slide,
            "deck includes a closing slide",
            len(contexts) - 1 if not has_closing_slide and contexts else None,
        ),
        "visual_rhythm": (len(content_kinds) >= 2, f"content mix={sorted(content_kinds)}", None),
        "theme_consistent": (theme_consistent, f"font families={sorted(_all_font_families(deck))}", None),
        "not_same_layout_everywhere": (len(unique_layouts) > 1, f"{len(unique_layouts)} unique layouts", None),
        "no_generic_titles": (generic_title_failures == 0, f"{generic_title_failures} generic titles", None),
        "not_bullet_wall_deck": (
            bullet_wall_slides < max(2, len(contexts) // 2),
            f"{bullet_wall_slides} bullet-heavy slides",
            None,
        ),
        "no_empty_visual_slots": (
            empty_visual_slot_failures == 0,
            f"{empty_visual_slot_failures} slides with empty visual slots",
            None,
        ),
        "title_capitalization_consistent": (
            len([style for style, count in title_styles.items() if count > 0 and style != "empty"]) <= 2,
            f"title capitalization styles={dict(title_styles)}",
            None,
        ),
        "not_auto_generated": (
            repetitive_titles == 0 and max_run < 3,
            f"repeated_titles={repetitive_titles}, longest_layout_run={max_run}",
            None,
        ),
    }


def _first_impression(contexts: list[SlideContext], overall_grade: str, *, unique_layouts: int) -> dict[str, str]:
    bullet_heavy = sum(1 for context in contexts if len([block for block in _body_blocks(context.body_nodes) if block.type == "bullet"]) >= 5)
    chart_slides = sum(1 for context in contexts if context.chart_nodes)
    image_slides = sum(1 for context in contexts if any(node.image_path for node in context.image_nodes))

    if bullet_heavy >= max(2, len(contexts) // 2):
        communicates = "The deck communicates a text-heavy story that needs sharper visual distillation."
    elif chart_slides or image_slides:
        communicates = "The deck communicates an evidence-led story with visible support from charts or imagery."
    else:
        communicates = "The deck communicates the core story, but leans heavily on text."

    if unique_layouts <= 1:
        rhythm = "The visual rhythm is repetitive because the same layout carries most of the argument."
    elif unique_layouts >= 3:
        rhythm = "The visual rhythm is varied enough to keep the story moving slide to slide."
    else:
        rhythm = "The visual rhythm has some variation, but it still clusters around a narrow layout range."

    return {
        "communicates": communicates,
        "visual_rhythm": rhythm,
        "glance_grade": overall_grade,
    }


def generate_review_report(deck: Deck, provider: LayoutProvider, screenshot_paths: list[Path], *, artifacts_dir: Path) -> dict[str, Any]:
    contexts = _make_slide_contexts(deck, provider, screenshot_paths)
    heading_sizes = [
        _computed(context.slide, context.title_node).font_size_pt
        for context in contexts
        if context.title_node is not None and _computed(context.slide, context.title_node) is not None
    ] or [32.0]
    body_sizes = [
        _computed(context.slide, node).font_size_pt
        for context in contexts
        for node in context.body_nodes
        if _computed(context.slide, node) is not None
    ] or [18.0]
    deck_families = _all_font_families(deck)

    slide_results = [
        _slide_checks(
            context,
            median_heading_size=median(heading_sizes),
            median_body_size=median(body_sizes),
            deck_families=deck_families,
        )
        for context in contexts
    ]
    deck_level = _deck_level_checks(contexts, deck)

    categories: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    checklist_total = 0
    checklist_passed = 0

    for category_name, items in CHECKLIST.items():
        passed_items = 0
        item_results: list[dict[str, Any]] = []
        for item in items:
            item_key = item["key"]
            item_label = item["label"]
            if category_name in {"Deck-Level Patterns", "AI Slop Detection"}:
                passed, detail, slide_index = deck_level[item_key]
                failures = 0 if passed else 1
            else:
                passed, failures = _aggregate_item_status(slide_results, item_key)
                detail = "passes on all reviewed slides" if passed else f"fails on {failures} slide(s)"
                slide_index = None
                if not passed:
                    for index, result in enumerate(slide_results):
                        if item_key in result and not result[item_key][0]:
                            slide_index = index
                            detail = result[item_key][1]
                            break

            if passed:
                passed_items += 1
                checklist_passed += 1
            else:
                severity = int(ITEM_METADATA[item_key]["severity"])
                screenshot = contexts[slide_index].screenshot_path if slide_index is not None else None
                issues.append(
                    {
                        "category": category_name,
                        "item": item_label,
                        "severity": severity,
                        "slide": None if slide_index is None else slide_index + 1,
                        "detail": detail,
                        "recommendation": str(ITEM_METADATA[item_key]["recommendation"]),
                        "screenshot": None if screenshot is None else _relative_path(screenshot, artifacts_dir),
                    }
                )

            item_results.append(
                {
                    "key": item_key,
                    "label": item_label,
                    "passed": passed,
                    "detail": detail,
                }
            )

        checklist_total += len(items)
        ratio = passed_items / len(items)
        categories[category_name] = {
            "passed": passed_items,
            "total": len(items),
            "grade": _grade_from_ratio(ratio),
            "items": item_results,
        }

    slide_summaries: list[dict[str, Any]] = []
    for context, result in zip(contexts, slide_results):
        failures = [
            {
                "category": category_name,
                "item": item["label"],
                "detail": result[item["key"]][1],
            }
            for category_name, items in CHECKLIST.items()
            if category_name not in {"Deck-Level Patterns", "AI Slop Detection"}
            for item in items
            if item["key"] in result and not result[item["key"]][0]
        ]
        slide_summaries.append(
            {
                "slide": context.slide_index + 1,
                "slide_id": context.slide.slide_id,
                "layout": context.slide.layout,
                "title": _node_text(context.title_node) if context.title_node is not None else "",
                "screenshot": _relative_path(context.screenshot_path, artifacts_dir),
                "failed_checks": failures,
            }
        )

    issues.sort(key=lambda item: (-item["severity"], item["slide"] or 999))
    overall_ratio = checklist_passed / checklist_total if checklist_total else 1.0
    overall_grade = _grade_from_ratio(overall_ratio)
    first_impression = _first_impression(contexts, overall_grade, unique_layouts=len(set(context.slide.layout for context in contexts)))

    return {
        "deck": {
            "slides": len(deck.slides),
            "template": "template" if deck.template_manifest else "default",
        },
        "first_impression": first_impression,
        "categories": categories,
        "overall": {
            "grade": overall_grade,
            "passed": checklist_passed,
            "total": checklist_total,
        },
        "slides": slide_summaries,
        "top_issues": issues[:5],
        "all_issues": issues,
    }


def report_to_markdown(report: dict[str, Any], *, deck_name: str) -> str:
    lines = [
        "DECK VISUAL QA REPORT",
        "======================",
        f"Deck: {deck_name} ({report['deck']['slides']} slides)",
        f"Template: {report['deck']['template']}",
        "",
        "FIRST IMPRESSION",
        "----------------",
        report["first_impression"]["communicates"],
        report["first_impression"]["visual_rhythm"],
        f"If I had to grade this deck at a glance: {report['first_impression']['glance_grade']}.",
        "",
    ]

    for category_name, category in report["categories"].items():
        lines.append(
            f"{category_name}: {category['grade']} ({category['passed']}/{category['total']} items pass)"
        )
    lines.extend(
        [
            "",
            f"OVERALL: {report['overall']['grade']} ({report['overall']['passed']}/{report['overall']['total']} checklist items pass)",
            "",
            "TOP ISSUES",
            "----------",
        ]
    )

    if not report["top_issues"]:
        lines.append("No critical issues detected.")
    else:
        for index, issue in enumerate(report["top_issues"], start=1):
            slide_ref = f"Slide {issue['slide']}" if issue["slide"] is not None else "Deck"
            lines.append(f"{index}. {slide_ref}: {issue['item']} -> {issue['detail']}")
            lines.append(f"   Fix: {issue['recommendation']}")
            if issue["screenshot"] is not None:
                lines.append(f"   [screenshot: {issue['screenshot']}]")

    lines.extend(["", "SLIDE-BY-SLIDE AUDIT", "-------------------"])
    for slide in report["slides"]:
        lines.append(
            f"Slide {slide['slide']} ({slide['layout']}): {slide['title'] or '(untitled)'}"
        )
        if not slide["failed_checks"]:
            lines.append("  Pass")
            continue
        for failure in slide["failed_checks"]:
            lines.append(f"  - {failure['category']}: {failure['item']} -> {failure['detail']}")

    return "\n".join(lines) + "\n"


def _clone_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    return [TextBlock.model_validate(block.model_dump(mode="json")) for block in blocks]


def _set_text(node: Node, text: str) -> None:
    node.content = NodeContent.from_text(text)


def apply_review_fixes(deck_path: Path) -> list[dict[str, Any]]:
    def mutate(deck: Deck, provider: LayoutProvider) -> list[dict[str, Any]]:
        fixes: list[dict[str, Any]] = []
        index = 0
        while index < len(deck.slides):
            slide = deck.slides[index]
            slots = provider.get_layout(slide.layout).slots
            title_node = _find_title_node(slide, slots)
            context = SlideContext(
                slide=slide,
                slide_index=index,
                layout_slots=slots,
                title_node=title_node,
                text_nodes=[node for node in slide.nodes if node.type == "text" and _node_text(node)],
                body_nodes=[
                    node
                    for node in slide.nodes
                    if node.type == "text" and _role_for_node(node, slots) in {"body", "quote", "attribution"}
                ],
                chart_nodes=[node for node in slide.nodes if node.type == "chart"],
                image_nodes=[node for node in slide.nodes if node.type == "image"],
                screenshot_path=Path(f"slide-{index + 1:02d}.png"),
            )

            rewritten_title = _title_rewrite(context)
            if rewritten_title and title_node is not None and rewritten_title != _node_text(title_node):
                _set_text(title_node, rewritten_title)
                fixes.append({"slide": index + 1, "type": "rewrite_title", "value": rewritten_title})

            for chart_node in context.chart_nodes:
                chart = chart_node.chart_spec
                if chart is None or chart.title:
                    continue
                chart.title = _default_chart_title(context, chart_node)
                fixes.append({"slide": index + 1, "type": "chart_title", "value": chart.title})

            if slide.layout == "title_content":
                body_nodes = [node for node in context.body_nodes if node.slot_binding == "body"]
                if len(body_nodes) == 1:
                    body_node = body_nodes[0]
                    bullet_blocks = [block for block in _node_blocks(body_node) if block.type == "bullet"]
                    if len(bullet_blocks) > 6:
                        split_at = len(bullet_blocks) // 2
                        leading_blocks = [block for block in _node_blocks(body_node) if block.type != "bullet"]
                        first_half = _clone_blocks(leading_blocks + bullet_blocks[:split_at])
                        second_half = _clone_blocks(bullet_blocks[split_at:])
                        body_node.content = NodeContent(blocks=first_half)
                        follow_up = Slide(
                            slide_id=deck.next_slide_id(),
                            layout="title_content",
                            nodes=[
                                Node(
                                    node_id=deck.next_node_id(),
                                    slot_binding="heading",
                                    type="text",
                                    content=NodeContent.from_text(
                                        f"{_node_text(title_node) if title_node is not None else 'Supporting detail'} (continued)"
                                    ),
                                ),
                                Node(
                                    node_id=deck.next_node_id(),
                                    slot_binding="body",
                                    type="text",
                                    content=NodeContent(blocks=second_half),
                                ),
                            ],
                        )
                        deck.slides.insert(index + 1, follow_up)
                        fixes.append(
                            {
                                "slide": index + 1,
                                "type": "split_bullets",
                                "value": f"Created slide {follow_up.slide_id}",
                            }
                        )
                        index += 1
            index += 1

        return fixes

    _, result = mutate_deck(str(deck_path), mutate)
    return result


def review_deck(deck_path: Path, output_dir: Path, *, dpi: int = 200, fix: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    before_dir = output_dir / ("before" if fix else "run")
    before_dir.mkdir(parents=True, exist_ok=True)

    before_pptx = before_dir / f"{deck_path.stem}.pptx"
    before_deck, before_provider = _build_deck_artifact(deck_path, before_pptx)
    _, before_pngs = render_pptx_to_pngs(before_pptx, before_dir, dpi=dpi)
    before_report = generate_review_report(before_deck, before_provider, before_pngs, artifacts_dir=output_dir)

    report: dict[str, Any] = {
        "before": before_report,
        "fixes_applied": [],
    }

    if fix:
        fixes = apply_review_fixes(deck_path)
        report["fixes_applied"] = fixes
        after_dir = output_dir / "after"
        after_dir.mkdir(parents=True, exist_ok=True)
        after_pptx = after_dir / f"{deck_path.stem}.pptx"
        after_deck, after_provider = _build_deck_artifact(deck_path, after_pptx)
        _, after_pngs = render_pptx_to_pngs(after_pptx, after_dir, dpi=dpi)
        after_report = generate_review_report(after_deck, after_provider, after_pngs, artifacts_dir=output_dir)
        report["after"] = after_report
        report["comparison"] = {
            "before_grade": before_report["overall"]["grade"],
            "after_grade": after_report["overall"]["grade"],
        }
        report["active"] = after_report
    else:
        report["active"] = before_report

    active_markdown = report_to_markdown(report["active"], deck_name=deck_path.name)
    if fix and report["fixes_applied"]:
        active_markdown += "\nAUTO-FIX SUMMARY\n----------------\n"
        for fix_item in report["fixes_applied"]:
            active_markdown += f"- Slide {fix_item['slide']}: {fix_item['type']} -> {fix_item['value']}\n"
        comparison = report.get("comparison")
        if comparison is not None:
            active_markdown += (
                f"\nBefore/after overall grade: {comparison['before_grade']} -> {comparison['after_grade']}\n"
            )

    report_md_path = output_dir / "report.md"
    report_json_path = output_dir / "report.json"
    report_md_path.write_text(active_markdown, encoding="utf-8")
    report_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_md_path)
    report["report_json_path"] = str(report_json_path)
    return report
