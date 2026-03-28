"""PowerPoint writer for scene-graph decks."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Emu, Inches, Pt

from agent_slides.model.types import ComputedNode, Deck, EMU_PER_POINT, Node

BLANK_LAYOUT_INDEX = 6


def points_to_emu(value_pt: float) -> Emu:
    """Convert points to EMU for python-pptx geometry APIs."""

    return Emu(int(round(value_pt * EMU_PER_POINT)))


def hex_to_rgb(value: str) -> RGBColor:
    """Convert a #RRGGBB-style color string into an RGBColor."""

    normalized = value.lstrip("#")
    return RGBColor.from_string(normalized)


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

    lines = node.content.split("\n")
    for index, line in enumerate(lines):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        run = paragraph.add_run()
        run.text = line
        run.font.name = computed.font_family
        run.font.size = Pt(computed.font_size_pt)
        run.font.bold = computed.font_bold
        run.font.color.rgb = hex_to_rgb(computed.color)


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

            render_text_node(pptx_slide.shapes, node, computed)

    presentation.save(Path(output_path))
