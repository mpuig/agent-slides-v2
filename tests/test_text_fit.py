from __future__ import annotations

from agent_slides.engine.text_fit import fit_text


def test_short_text_fits_at_default_size() -> None:
    assert fit_text("Hello world", width=200, height=80, default_size=32) == (32, False)


def test_medium_text_shrinks_until_it_fits() -> None:
    font_size, overflowed = fit_text("A" * 60, width=180, height=100, default_size=32)

    assert font_size == 20
    assert overflowed is False


def test_long_text_overflows_at_min_size() -> None:
    assert fit_text("A" * 500, width=120, height=60, default_size=24) == (10.0, True)


def test_empty_text_returns_default_size() -> None:
    assert fit_text("", width=120, height=60, default_size=24) == (24, False)


def test_single_character_returns_default_size() -> None:
    assert fit_text("A", width=20, height=20, default_size=32) == (32, False)


def test_very_long_text_shrinks_to_min_size_and_overflows() -> None:
    assert fit_text("A" * 10_000, width=500, height=200, default_size=24) == (10.0, True)


def test_zero_width_returns_min_size_with_overflow() -> None:
    assert fit_text("Hello", width=0, height=60, default_size=24) == (10.0, True)


def test_shrinking_happens_in_two_point_steps() -> None:
    font_size, overflowed = fit_text("A" * 50, width=180, height=170, default_size=32)

    assert font_size == 28
    assert overflowed is False
