"""PowerPoint writer for scene-graph decks."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Emu, Inches, Pt

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.model.types import ComputedNode, Deck, EMU_PER_POINT, Node, TextBlock

BLANK_LAYOUT_INDEX = 6
HEADING_SIZE_FACTOR = 1.35
TEMPLATE_CHANGED = "TEMPLATE_CHANGED"


@dataclass(frozen=True)
class TemplateLayoutBinding:
    master_index: int
    layout_index: int
    slot_mapping: dict[str, int]


class TemplateLayoutRegistry:
    """Read template manifest metadata needed by the PPTX writer."""

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        payload = _read_manifest_payload(self.manifest_path)
        self._source = _require_string(payload, "source")
        self._source_hash = _require_string(payload, "source_hash")
        self._layouts = _read_layout_bindings(payload)

    @property
    def source_hash(self) -> str:
        return self._source_hash

    @property
    def source_path(self) -> Path:
        return (self.manifest_path.parent / self._source).resolve()

    def binding_for(self, slug: str) -> TemplateLayoutBinding:
        binding = self._layouts.get(slug)
        if binding is None:
            raise AgentSlidesError(
                SCHEMA_ERROR,
                f"Template manifest does not define layout '{slug}'",
                details={"layout": slug, "manifest": str(self.manifest_path)},
            )
        return binding


def points_to_emu(value_pt: float) -> Emu:
    """Convert points to EMU for python-pptx geometry APIs."""

    return Emu(int(round(value_pt * EMU_PER_POINT)))


def hex_to_rgb(value: str) -> RGBColor:
    """Convert a #RRGGBB-style color string into an RGBColor."""

    normalized = value.lstrip("#")
    return RGBColor.from_string(normalized)


def _block_font_size(computed: ComputedNode, block: TextBlock) -> float:
    if block.type == "heading":
        return computed.font_size_pt * HEADING_SIZE_FACTOR
    return computed.font_size_pt


def _block_lines(block: TextBlock) -> list[str]:
    lines = block.text.splitlines()
    return lines or [""]


def _block_text(block: TextBlock, line: str) -> str:
    if block.type == "bullet":
        return f"• {line}" if line else "•"
    return line


def _read_manifest_payload(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Manifest file not found: {path}") from exc
    except OSError as exc:
        raise AgentSlidesError(SCHEMA_ERROR, f"Failed to read manifest file {path}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest file is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Manifest root must be a JSON object.")
    return payload


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be a non-empty string.")
    return value


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an array.")
    return value


def _require_dict(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be an object.")
    return value


def _require_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or value < 0:
        raise AgentSlidesError(SCHEMA_ERROR, f"Manifest field '{field}' must be a non-negative integer.")
    return value


def _read_layout_bindings(payload: dict[str, Any]) -> dict[str, TemplateLayoutBinding]:
    bindings: dict[str, TemplateLayoutBinding] = {}

    for master_position, master in enumerate(_require_list(payload, "slide_masters")):
        if not isinstance(master, dict):
            raise AgentSlidesError(SCHEMA_ERROR, f"Manifest slide_masters[{master_position}] must be an object.")

        for layout_position, layout in enumerate(_require_list(master, "layouts")):
            if not isinstance(layout, dict):
                raise AgentSlidesError(
                    SCHEMA_ERROR,
                    f"Manifest slide_masters[{master_position}].layouts[{layout_position}] must be an object.",
                )

            slug = _require_string(layout, "slug")
            slot_mapping = _require_dict(layout, "slot_mapping")
            binding = TemplateLayoutBinding(
                master_index=layout.get("master_index", master_position),
                layout_index=layout.get("index", layout_position),
                slot_mapping={slot: _require_int(slot_mapping, slot) for slot in slot_mapping},
            )
            if slug in bindings:
                raise AgentSlidesError(SCHEMA_ERROR, f"Manifest layout slug '{slug}' must be unique.")
            bindings[slug] = binding

    return bindings


def _content_lines(node: Node) -> list[str]:
    if isinstance(node.content, str):
        return node.content.split("\n")

    lines: list[str] = []
    for block in node.content.blocks:
        lines.extend(_block_text(block, line) for line in _block_lines(block))
    return lines or [""]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _emit_warning(code: str, message: str) -> None:
    payload = {"warning": {"code": code, "message": message}}
    sys.stderr.write(f"{json.dumps(payload)}\n")


def _warn_if_template_changed(template_path: Path, expected_hash: str) -> None:
    actual_hash = _sha256(template_path)
    if actual_hash == expected_hash:
        return

    _emit_warning(
        TEMPLATE_CHANGED,
        f"Template source hash mismatch for {template_path}: manifest={expected_hash} actual={actual_hash}",
    )


def _delete_all_slides(prs: Presentation) -> None:
    """Remove every slide from a presentation while keeping masters and layouts."""

    slide_ids = list(prs.slides._sldIdLst)
    for slide_id in slide_ids:
        prs.slides._sldIdLst.remove(slide_id)
        prs.part.drop_rel(slide_id.rId)


def _resolve_layout(prs: Presentation, slide_layout: str, binding: TemplateLayoutBinding):
    try:
        slide_master = prs.slide_masters[binding.master_index]
    except IndexError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            (
                f"Template layout '{slide_layout}' references missing master index "
                f"{binding.master_index}"
            ),
            details={
                "layout": slide_layout,
                "master_index": binding.master_index,
                "layout_index": binding.layout_index,
            },
        ) from exc

    try:
        return slide_master.slide_layouts[binding.layout_index]
    except IndexError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            (
                f"Template layout '{slide_layout}' references missing layout index "
                f"{binding.layout_index} in master {binding.master_index}"
            ),
            details={
                "layout": slide_layout,
                "master_index": binding.master_index,
                "layout_index": binding.layout_index,
            },
        ) from exc


def _fill_placeholder(node: Node, slot_mapping: dict[str, int], slide) -> None:
    if node.slot_binding is None or node.type != "text":
        return

    placeholder_idx = slot_mapping.get(node.slot_binding)
    if placeholder_idx is None:
        return

    placeholder = slide.placeholders[placeholder_idx]
    text_frame = placeholder.text_frame
    text_frame.clear()

    lines = _content_lines(node)
    text_frame.paragraphs[0].add_run().text = lines[0]
    for line in lines[1:]:
        paragraph = text_frame.add_paragraph()
        paragraph.add_run().text = line


def _write_template_pptx(deck: Deck, output_path: str) -> None:
    registry = TemplateLayoutRegistry(deck.template_manifest)
    template_path = registry.source_path

    if not template_path.exists():
        raise AgentSlidesError(FILE_NOT_FOUND, f"Template file not found: {template_path}")

    _warn_if_template_changed(template_path, registry.source_hash)
    presentation = Presentation(template_path)
    _delete_all_slides(presentation)

    for slide in deck.slides:
        binding = registry.binding_for(slide.layout)
        pptx_slide = presentation.slides.add_slide(_resolve_layout(presentation, slide.layout, binding))
        for node in slide.nodes:
            _fill_placeholder(node, binding.slot_mapping, pptx_slide)

    presentation.save(Path(output_path))


def render_text_node(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
    """Render a single text node as a positioned text box."""

    shape = slide_shape_collection.add_textbox(
        points_to_emu(computed.x),
        points_to_emu(computed.y),
        points_to_emu(computed.width),
        points_to_emu(computed.height),
    )
    shape.line.fill.background()

    if computed.bg_color is not None:
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(computed.bg_color)
        shape.fill.transparency = computed.bg_transparency
    else:
        shape.fill.background()

    text_frame = shape.text_frame
    text_frame.clear()
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    text_frame.margin_left = 0
    text_frame.margin_right = 0
    text_frame.margin_top = 0
    text_frame.margin_bottom = 0

    blocks = node.content.blocks or [TextBlock(type="paragraph", text="")]
    paragraph_index = 0
    for block in blocks:
        for line in _block_lines(block):
            paragraph = (
                text_frame.paragraphs[0]
                if paragraph_index == 0
                else text_frame.add_paragraph()
            )
            paragraph.level = block.level if block.type == "bullet" else 0

            run = paragraph.add_run()
            run.text = _block_text(block, line)
            run.font.name = computed.font_family
            run.font.size = Pt(_block_font_size(computed, block))
            run.font.bold = computed.font_bold or block.type == "heading"
            run.font.color.rgb = hex_to_rgb(computed.color)
            paragraph_index += 1


def render_image_node(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
    """Render a single image node into its computed frame."""

    if not node.image_path:
        return

    slide_shape_collection.add_picture(
        node.image_path,
        points_to_emu(computed.x),
        points_to_emu(computed.y),
        width=points_to_emu(computed.width),
        height=points_to_emu(computed.height),
    )


def _write_v0_pptx(deck: Deck, output_path: str) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(10)
    presentation.slide_height = Inches(7.5)
    blank_layout = presentation.slide_layouts[BLANK_LAYOUT_INDEX]

    for slide in deck.slides:
        pptx_slide = presentation.slides.add_slide(blank_layout)
        if not slide.computed:
            continue

        for node in slide.nodes:
            if node.slot_binding is None:
                continue

            computed = slide.computed.get(node.node_id)
            if computed is None:
                continue

            if node.type == "image":
                render_image_node(pptx_slide.shapes, node, computed)
            else:
                render_text_node(pptx_slide.shapes, node, computed)

    presentation.save(Path(output_path))


def write_pptx(deck: Deck, output_path: str) -> None:
    """Write a deck to PowerPoint using either the v0 or template-backed writer."""

    if deck.template_manifest:
        _write_template_pptx(deck, output_path)
        return

    _write_v0_pptx(deck, output_path)
