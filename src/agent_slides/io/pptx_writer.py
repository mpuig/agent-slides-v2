"""PowerPoint writer for scene-graph decks."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.parts.image import Image
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Emu, Inches, Pt

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR, TEMPLATE_CHANGED
from agent_slides.icons import ICON_VIEWBOX, require_icon, svg_path_subpaths
from agent_slides.io.assets import resolve_image_path
from agent_slides.model.types import ComputedNode, Deck, EMU_PER_POINT, Node, TextBlock

BLANK_LAYOUT_INDEX = 6
HEADING_SIZE_FACTOR = 1.35
BULLET_MARGIN_STEP_PT = 18.0
BLOCK_SPACING_FACTOR = 0.3
LINE_HEIGHT_FACTOR = 1.2
ICON_BULLET_SIZE_FACTOR = 0.78
ICON_BULLET_GAP_FACTOR = 0.4
CHART_TYPE_MAP = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie": XL_CHART_TYPE.PIE,
    "area": XL_CHART_TYPE.AREA,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}


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


def _block_line_height(computed: ComputedNode, block: TextBlock) -> float:
    return _block_font_size(computed, block) * LINE_HEIGHT_FACTOR


def _icon_bullet_indent(block: TextBlock, computed: ComputedNode | None = None) -> float:
    font_size = computed.font_size_pt if computed is not None else 14.0
    icon_size = font_size * ICON_BULLET_SIZE_FACTOR
    icon_gap = font_size * ICON_BULLET_GAP_FACTOR
    return (block.level * BULLET_MARGIN_STEP_PT) + icon_size + icon_gap


def _block_lines(block: TextBlock) -> list[str]:
    lines = block.text.splitlines()
    return lines or [""]


def _fit_image_to_slot(computed: ComputedNode, image_size_px: tuple[int, int]) -> tuple[float, float, float, float]:
    slot_x = computed.x
    slot_y = computed.y
    slot_width = computed.width
    slot_height = computed.height

    if computed.image_fit == "stretch":
        return slot_x, slot_y, slot_width, slot_height

    image_width_px, image_height_px = image_size_px
    if computed.image_fit == "cover":
        scale = max(slot_width / image_width_px, slot_height / image_height_px)
    else:
        scale = min(slot_width / image_width_px, slot_height / image_height_px)
    width = image_width_px * scale
    height = image_height_px * scale
    return (
        slot_x + ((slot_width - width) / 2),
        slot_y + ((slot_height - height) / 2),
        width,
        height,
    )


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


def _node_paragraphs(node: Node) -> list[tuple[TextBlock, str]]:
    if isinstance(node.content, str):
        block = TextBlock(type="paragraph", text=node.content)
        return [(block, line) for line in _block_lines(block)]

    paragraphs: list[tuple[TextBlock, str]] = []
    for block in node.content.blocks:
        paragraphs.extend((block, line) for line in _block_lines(block))
    return paragraphs or [(TextBlock(type="paragraph", text=""), "")]


def _configure_paragraph_bullets(paragraph, block: TextBlock, *, computed: ComputedNode | None = None) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pPr.remove_all("a:buNone", "a:buAutoNum", "a:buChar", "a:buBlip")

    if block.type == "bullet":
        pPr.lvl = block.level
        if block.icon:
            pPr.insert_element_before(OxmlElement("a:buNone"), "a:tabLst", "a:defRPr", "a:extLst")
            pPr.set("marL", str(Pt(_icon_bullet_indent(block, computed))))
            pPr.set("indent", "0")
            return
        buChar = OxmlElement("a:buChar")
        buChar.set("char", "•")
        pPr.insert_element_before(buChar, "a:tabLst", "a:defRPr", "a:extLst")
        pPr.set("marL", str(Pt(BULLET_MARGIN_STEP_PT * (block.level + 1))))
        pPr.set("indent", str(Pt(-BULLET_MARGIN_STEP_PT)))
        return

    pPr.lvl = 0
    for attr_name in ("marL", "indent"):
        if attr_name in pPr.attrib:
            del pPr.attrib[attr_name]
    pPr.insert_element_before(OxmlElement("a:buNone"), "a:tabLst", "a:defRPr", "a:extLst")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _emit_warning(payload: dict[str, object]) -> None:
    sys.stderr.write(f"{json.dumps(payload)}\n")


def _warn_if_template_changed(template_path: Path, expected_hash: str) -> None:
    actual_hash = _sha256(template_path)
    if actual_hash == expected_hash:
        return

    _emit_warning(
        {
            "warning": {
                "code": TEMPLATE_CHANGED,
                "message": "Template source file changed since the manifest was learned.",
            },
            "data": {
                "template": str(template_path),
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        }
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

    paragraphs = _node_paragraphs(node)
    for paragraph_index, (block, line) in enumerate(paragraphs):
        paragraph = text_frame.paragraphs[0] if paragraph_index == 0 else text_frame.add_paragraph()
        _configure_paragraph_bullets(paragraph, block)
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
            if node.type == "icon":
                computed = slide.computed.get(node.node_id)
                if computed is not None:
                    _render_icon_node(pptx_slide.shapes, node, computed)
                continue
            _fill_placeholder(node, binding.slot_mapping, pptx_slide)

    presentation.save(Path(output_path))


def _render_text_node(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
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
            paragraph = text_frame.paragraphs[0] if paragraph_index == 0 else text_frame.add_paragraph()
            _configure_paragraph_bullets(paragraph, block, computed=computed)

            run = paragraph.add_run()
            run.text = line
            run.font.name = computed.font_family
            run.font.size = Pt(_block_font_size(computed, block))
            run.font.bold = computed.font_bold or block.type == "heading"
            run.font.color.rgb = hex_to_rgb(computed.color)
            paragraph_index += 1

    _render_text_block_icons(slide_shape_collection, node, computed)


def _render_icon_shape(
    slide_shape_collection: SlideShapes,
    *,
    path_data: str,
    x: float,
    y: float,
    size: float,
    color: str,
) -> None:
    scale = size / ICON_VIEWBOX
    for subpath in svg_path_subpaths(path_data):
        points = [(x + (px * scale), y + (py * scale)) for px, py in subpath]
        if len(points) < 2:
            continue
        is_closed = points[0] == points[-1]
        vertices = points[1:-1] if is_closed else points[1:]
        builder = slide_shape_collection.build_freeform(
            points_to_emu(points[0][0]),
            points_to_emu(points[0][1]),
        )
        if vertices:
            builder.add_line_segments(
                tuple((points_to_emu(px), points_to_emu(py)) for px, py in vertices),
                close=is_closed,
            )
        shape = builder.convert_to_shape()
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(color)
        shape.line.fill.background()


def _render_text_block_icons(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
    blocks = node.content.blocks or [TextBlock(type="paragraph", text="")]
    current_y = computed.y
    for index, block in enumerate(blocks):
        line_height = _block_line_height(computed, block)
        for line in _block_lines(block):
            if block.type == "bullet" and block.icon:
                icon_size = computed.font_size_pt * ICON_BULLET_SIZE_FACTOR
                icon_x = computed.x + (block.level * BULLET_MARGIN_STEP_PT)
                icon_y = current_y + ((line_height - icon_size) / 2)
                _render_icon_shape(
                    slide_shape_collection,
                    path_data=require_icon(block.icon),
                    x=icon_x,
                    y=icon_y,
                    size=icon_size,
                    color=computed.color,
                )
            current_y += line_height
        if index < len(blocks) - 1:
            current_y += computed.font_size_pt * BLOCK_SPACING_FACTOR


def _render_image_node(
    slide_shape_collection: SlideShapes,
    node: Node,
    computed: ComputedNode,
    *,
    asset_base_dir: str | Path | None = None,
) -> None:
    """Render a single image node as a positioned picture."""

    if node.image_path is None:
        return

    image_path = resolve_image_path(node.image_path, base_dir=asset_base_dir)
    image = Image.from_file(str(image_path))
    left, top, width, height = _fit_image_to_slot(computed, cast(tuple[int, int], image.size))
    slide_shape_collection.add_picture(
        str(image_path),
        points_to_emu(left),
        points_to_emu(top),
        width=points_to_emu(width),
        height=points_to_emu(height),
    )
def _render_chart_node(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
    """Render a single chart node as a native editable PowerPoint chart."""

    spec = node.chart_spec
    if spec is None:
        return

    if spec.chart_type == "scatter":
        chart_data = XyChartData()
        for scatter_series in spec.scatter_series:
            series = chart_data.add_series(scatter_series.name)
            for point in scatter_series.points:
                series.add_data_point(point.x, point.y)
        pptx_type = XL_CHART_TYPE.XY_SCATTER
    else:
        chart_data = CategoryChartData()
        chart_data.categories = spec.categories
        for category_series in spec.series:
            chart_data.add_series(category_series.name, category_series.values)
        pptx_type = CHART_TYPE_MAP[spec.chart_type]

    chart_frame = slide_shape_collection.add_chart(
        pptx_type,
        points_to_emu(computed.x),
        points_to_emu(computed.y),
        points_to_emu(computed.width),
        points_to_emu(computed.height),
        chart_data,
    )
    chart = chart_frame.chart

    if spec.title:
        chart.has_title = True
        chart.chart_title.text_frame.text = spec.title
    chart.has_legend = spec.style.has_legend

    # Native PowerPoint charts do not inherit agent-slides theme colors.
    for index, color in enumerate(spec.style.series_colors or []):
        if index >= len(chart.series):
            break
        fill = chart.series[index].format.fill
        fill.solid()
        fill.fore_color.rgb = hex_to_rgb(color)


def _render_icon_node(slide_shape_collection: SlideShapes, node: Node, computed: ComputedNode) -> None:
    path_data = computed.icon_svg_path or require_icon(str(node.icon_name))
    _render_icon_shape(
        slide_shape_collection,
        path_data=path_data,
        x=computed.x,
        y=computed.y,
        size=computed.width,
        color=computed.color,
    )


render_text_node = _render_text_node
render_image_node = _render_image_node
render_icon_node = _render_icon_node


def _write_v0_pptx(deck: Deck, output_path: str, *, asset_base_dir: str | Path | None = None) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(10)
    presentation.slide_height = Inches(7.5)
    blank_layout = presentation.slide_layouts[BLANK_LAYOUT_INDEX]

    for slide in deck.slides:
        pptx_slide = presentation.slides.add_slide(blank_layout)
        if not slide.computed:
            continue

        for node in slide.nodes:
            if node.slot_binding is None and node.type != "icon":
                continue

            computed = slide.computed.get(node.node_id)
            if computed is None:
                continue

            if node.type == "chart":
                _render_chart_node(pptx_slide.shapes, node, computed)
            elif node.type == "icon":
                _render_icon_node(pptx_slide.shapes, node, computed)
            elif node.type == "image":
                _render_image_node(
                    pptx_slide.shapes,
                    node,
                    computed,
                    asset_base_dir=asset_base_dir,
                )
            else:
                _render_text_node(pptx_slide.shapes, node, computed)

    presentation.save(Path(output_path))


def write_pptx(deck: Deck, output_path: str, *, asset_base_dir: str | Path | None = None) -> None:
    """Write a deck to PowerPoint using either the v0 or template-backed writer."""

    if deck.template_manifest:
        _write_template_pptx(deck, output_path)
        return

    _write_v0_pptx(deck, output_path, asset_base_dir=asset_base_dir)
