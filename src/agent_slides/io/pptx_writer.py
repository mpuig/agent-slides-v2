"""PowerPoint writer for scene-graph decks."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Emu, Inches, Pt

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


def write_pptx(deck: Deck, output_path: str) -> None:
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
                render_image_node(pptx_slide.shapes, node, computed)
            else:
                render_text_node(pptx_slide.shapes, node, computed)

    presentation.save(Path(output_path))
