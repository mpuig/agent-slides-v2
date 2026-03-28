from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches, Pt

from agent_slides.io.pptx_writer import write_pptx
from agent_slides.model.types import (
    ComputedNode,
    Counters,
    Deck,
    EMU_PER_POINT,
    Node,
    NodeContent,
    Slide,
    TextBlock,
)


def build_deck() -> Deck:
    return Deck(
        deck_id="deck-1",
        revision=4,
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content="Heading line 1\nHeading line 2",
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding=None,
                        type="text",
                        content="Should not render",
                    ),
                    Node(
                        node_id="n-3",
                        slot_binding="body",
                        type="text",
                        content="",
                    ),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=54.0,
                        width=576.0,
                        height=96.0,
                        font_size_pt=28.0,
                        font_family="Aptos",
                        color="#112233",
                        bg_color="#F1E2D3",
                        font_bold=True,
                        revision=4,
                    ),
                    "n-2": ComputedNode(
                        x=10.0,
                        y=10.0,
                        width=100.0,
                        height=20.0,
                        font_size_pt=12.0,
                        font_family="Aptos",
                        color="#000000",
                        bg_color=None,
                        font_bold=False,
                        revision=4,
                    ),
                    "n-3": ComputedNode(
                        x=90.0,
                        y=180.0,
                        width=400.0,
                        height=40.0,
                        font_size_pt=18.0,
                        font_family="Calibri",
                        color="#445566",
                        bg_color=None,
                        font_bold=False,
                        revision=4,
                    ),
                },
            ),
            Slide(
                slide_id="s-2",
                layout="body",
                nodes=[
                    Node(
                        node_id="n-4",
                        slot_binding="body",
                        type="text",
                        content="Computed missing is skipped",
                    )
                ],
                computed={},
            ),
        ],
        counters=Counters(slides=2, nodes=4),
    )


def open_presentation(path: Path) -> Presentation:
    return Presentation(path)


def test_write_pptx_renders_expected_slides_and_shapes(tmp_path: Path) -> None:
    output_path = tmp_path / "deck.pptx"

    write_pptx(build_deck(), str(output_path))

    presentation = open_presentation(output_path)

    assert len(presentation.slides) == 2
    assert presentation.slide_width == Inches(10)
    assert presentation.slide_height == Inches(7.5)

    first_slide = presentation.slides[0]
    assert len(first_slide.shapes) == 2

    heading_box = first_slide.shapes[0]
    assert heading_box.left == int(72.0 * EMU_PER_POINT)
    assert heading_box.top == int(54.0 * EMU_PER_POINT)
    assert heading_box.width == int(576.0 * EMU_PER_POINT)
    assert heading_box.height == int(96.0 * EMU_PER_POINT)
    assert heading_box.fill.fore_color.rgb == RGBColor.from_string("F1E2D3")

    text_frame = heading_box.text_frame
    assert text_frame.word_wrap is True
    assert text_frame.auto_size == MSO_AUTO_SIZE.NONE
    assert [paragraph.text for paragraph in text_frame.paragraphs] == [
        "Heading line 1",
        "Heading line 2",
    ]

    first_run = text_frame.paragraphs[0].runs[0]
    assert first_run.font.name == "Aptos"
    assert first_run.font.size == Pt(28)
    assert first_run.font.bold is True
    assert first_run.font.color.rgb == RGBColor.from_string("112233")

    empty_box = first_slide.shapes[1]
    assert empty_box.text == ""
    empty_run = empty_box.text_frame.paragraphs[0].runs[0]
    assert empty_run.font.name == "Calibri"
    assert empty_run.font.size == Pt(18)
    assert empty_run.font.bold is False
    assert empty_run.font.color.rgb == RGBColor.from_string("445566")

    second_slide = presentation.slides[1]
    assert len(second_slide.shapes) == 0


def test_write_pptx_creates_valid_empty_presentation(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.pptx"
    deck = Deck(deck_id="empty-deck")

    write_pptx(deck, str(output_path))

    presentation = open_presentation(output_path)

    assert output_path.exists()
    assert len(presentation.slides) == 0


def test_write_pptx_renders_structured_headings_and_bullets(tmp_path: Path) -> None:
    output_path = tmp_path / "structured.pptx"
    deck = Deck(
        deck_id="deck-structured",
        slides=[
            Slide(
                slide_id="s-1",
                layout="content",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="text",
                        content=NodeContent(
                            blocks=[
                                TextBlock(type="heading", text="Highlights"),
                                TextBlock(type="bullet", text="First takeaway"),
                                TextBlock(type="bullet", text="Nested takeaway", level=1),
                            ]
                        ),
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=54.0,
                        width=400.0,
                        height=140.0,
                        font_size_pt=20.0,
                        font_family="Aptos",
                        color="#112233",
                        bg_color=None,
                        font_bold=False,
                        revision=1,
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )

    write_pptx(deck, str(output_path))

    presentation = open_presentation(output_path)
    text_frame = presentation.slides[0].shapes[0].text_frame

    assert [paragraph.text for paragraph in text_frame.paragraphs] == [
        "Highlights",
        "• First takeaway",
        "• Nested takeaway",
    ]
    assert text_frame.paragraphs[0].runs[0].font.size == Pt(27)
    assert text_frame.paragraphs[1].level == 0
    assert text_frame.paragraphs[2].level == 1
