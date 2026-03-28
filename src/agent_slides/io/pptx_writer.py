"""PowerPoint writer for scene-graph decks."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.parts.image import Image
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Emu, Inches, Pt

from agent_slides.io.assets import resolve_image_path
from agent_slides.model.types import ComputedNode, Deck, EMU_PER_POINT, Node, TextBlock

BLANK_LAYOUT_INDEX = 6
HEADING_SIZE_FACTOR = 1.35


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


def _fit_image_to_slot(node: Node, computed: ComputedNode, image_size_px: tuple[int, int]) -> tuple[float, float, float, float]:
    slot_x = computed.x
    slot_y = computed.y
    slot_width = computed.width
    slot_height = computed.height

    if node.image_fit == "stretch":
        return slot_x, slot_y, slot_width, slot_height

    image_width_px, image_height_px = image_size_px
    scale = min(slot_width / image_width_px, slot_height / image_height_px)
    width = image_width_px * scale
    height = image_height_px * scale
    return (
        slot_x + ((slot_width - width) / 2),
        slot_y + ((slot_height - height) / 2),
        width,
        height,
    )


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


def render_image_node(
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
    left, top, width, height = _fit_image_to_slot(node, computed, cast(tuple[int, int], image.size))
    slide_shape_collection.add_picture(
        str(image_path),
        points_to_emu(left),
        points_to_emu(top),
        width=points_to_emu(width),
        height=points_to_emu(height),
    )


def write_pptx(deck: Deck, output_path: str, *, asset_base_dir: str | Path | None = None) -> None:
    """Write a deck to PowerPoint using the computed scene graph."""

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
                render_image_node(
                    pptx_slide.shapes,
                    node,
                    computed,
                    asset_base_dir=asset_base_dir,
                )
                continue

            render_text_node(pptx_slide.shapes, node, computed)

    presentation.save(Path(output_path))
