from __future__ import annotations

from PIL import ImageFont

from agent_slides.engine.text_fit import BlockFit, compose_blocks, fit_blocks, fit_text
from agent_slides.model.design_rules import BlockSpacingRules
from agent_slides.model.types import NodeContent, TextBlock, TextFitting


def test_short_text_fits_at_default_size() -> None:
    assert fit_text("Hello world", width=200, height=80, default_size=32, role="heading") == (32, False)


def test_body_text_uses_discrete_ladder_steps() -> None:
    font_size, overflowed = fit_text("A" * 60, width=96, height=140, default_size=18, role="body")

    assert font_size == 16
    assert overflowed is False


def test_long_text_overflows_at_min_size() -> None:
    assert fit_text("A" * 500, width=120, height=60, default_size=24, role="body") == (10.0, True)


def test_empty_text_returns_largest_ladder_size() -> None:
    assert fit_text("", width=120, height=60, role="quote") == (28.0, False)


def test_single_character_returns_default_size() -> None:
    assert fit_text("A", width=20, height=20, default_size=32, role="heading") == (32, False)


def test_very_long_text_shrinks_to_min_size_and_overflows() -> None:
    assert fit_text("A" * 10_000, width=500, height=200, default_size=24, role="body") == (10.0, True)


def test_zero_width_returns_smallest_ladder_size_with_overflow() -> None:
    assert fit_text("Hello", width=0, height=60, default_size=24, role="body") == (10.0, True)


def test_font_family_width_factors_change_selected_size() -> None:
    calibri_size, calibri_overflow = fit_text(
        "A" * 60,
        width=96,
        height=140,
        default_size=18,
        role="body",
        font_family="Calibri",
    )
    georgia_size, georgia_overflow = fit_text(
        "A" * 60,
        width=96,
        height=140,
        default_size=18,
        role="body",
        font_family="Georgia",
    )

    assert (calibri_size, calibri_overflow) == (18, False)
    assert (georgia_size, georgia_overflow) == (16, False)


def test_custom_ladder_overrides_default_and_minimum_sizes() -> None:
    font_size, overflowed = fit_text(
        "A" * 60,
        width=90,
        height=90,
        default_size=18,
        min_size=10,
        role="body",
        ladder=[18, 12],
    )

    assert font_size == 12
    assert overflowed is False


def test_structured_blocks_account_for_heading_hierarchy_and_spacing() -> None:
    content = NodeContent(
        blocks=[
            TextBlock(type="heading", text="Overview"),
            TextBlock(type="bullet", text="First key point"),
            TextBlock(type="bullet", text="Second key point"),
            TextBlock(type="bullet", text="Third key point"),
        ]
    )

    font_size, overflowed = fit_text(content, width=180, height=90, default_size=24, role="body")

    assert font_size == 14
    assert overflowed is False


def test_precise_measurement_uses_pillow_truetype(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    class FakeFont:
        def __init__(self, size: int) -> None:
            self.size = size

        def getlength(self, text: str) -> float:
            return len(text) * self.size * 0.9

        def getbbox(self, text: str) -> tuple[int, int, int, int]:
            width = max(int(len(text) * self.size * 0.9), 1)
            return (0, 0, width, self.size)

    def fake_truetype(font: str, size: int) -> FakeFont:
        calls.append((font, size))
        return FakeFont(size)

    monkeypatch.setattr(ImageFont, "truetype", fake_truetype)
    monkeypatch.setattr(ImageFont, "load_default", lambda: FakeFont(10))

    font_size, overflowed = fit_text(
        "A" * 18,
        width=60,
        height=60,
        default_size=18,
        role="body",
        font_family="DejaVuSans.ttf",
        ladder=[18, 12],
        use_precise=True,
    )

    assert font_size == 12
    assert overflowed is False
    assert calls == [("DejaVuSans.ttf", 18), ("DejaVuSans.ttf", 12)]


def test_fit_blocks_uses_heading_and_body_ladders_per_block() -> None:
    fits, overflowed = fit_blocks(
        [
            TextBlock(type="heading", text="Overview"),
            TextBlock(type="bullet", text="First point"),
            TextBlock(type="bullet", text="Second point"),
        ],
        width=240,
        height=160,
        role="body",
        text_fitting={
            "heading": TextFitting(default_size=32, min_size=24),
            "body": TextFitting(default_size=18, min_size=10),
        },
        spacing_rules=BlockSpacingRules(),
        type_ladders={
            "heading": [36.0, 32.0, 28.0, 24.0],
            "body": [18.0, 16.0, 14.0, 12.0, 10.0],
        },
    )

    assert [fit.font_size_pt for fit in fits] == [32.0, 18.0, 18.0]
    assert [fit.role for fit in fits] == ["heading", "body", "body"]
    assert overflowed is False


def test_compose_blocks_applies_padding_spacing_and_middle_alignment() -> None:
    block_fits = [
        BlockFit(
            block_index=0,
            block=TextBlock(type="heading", text="Overview"),
            role="heading",
            font_size_pt=24.0,
            rendered_height=26.4,
            line_count=1,
        ),
        BlockFit(
            block_index=1,
            block=TextBlock(type="bullet", text="First point"),
            role="body",
            font_size_pt=14.0,
            rendered_height=16.8,
            line_count=1,
        ),
    ]

    positions = compose_blocks(
        x=40.0,
        y=60.0,
        width=200.0,
        height=120.0,
        padding=8.0,
        vertical_align="middle",
        block_fits=block_fits,
        spacing_rules=BlockSpacingRules(),
    )

    assert positions[0].x == 48.0
    assert positions[0].width == 184.0
    assert positions[0].y == 93.4
    assert positions[1].y == 129.8
