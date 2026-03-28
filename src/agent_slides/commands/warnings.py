"""Helpers for surfacing non-fatal CLI warnings."""

from __future__ import annotations

from agent_slides.engine.validator import LAYOUT_FALLBACK
from agent_slides.model import Deck, Slide


def _fallback_warning(slide: Slide) -> dict[str, object] | None:
    for computed in slide.computed.values():
        if computed.layout_used is None or computed.layout_used == slide.layout:
            continue
        warning: dict[str, object] = {
            "code": LAYOUT_FALLBACK,
            "layout_used": computed.layout_used,
            "original": slide.layout,
        }
        if computed.layout_fallback_reason:
            warning["reason"] = computed.layout_fallback_reason
        return warning
    return None


def attach_layout_fallback_warning(
    payload: dict[str, object],
    deck: Deck,
    *,
    slide_ids: list[str] | None = None,
) -> dict[str, object]:
    if slide_ids is None:
        slides = deck.slides
    else:
        wanted = set(slide_ids)
        slides = [slide for slide in deck.slides if slide.slide_id in wanted]

    warnings = [warning for slide in slides if (warning := _fallback_warning(slide)) is not None]
    if not warnings:
        return payload
    if len(warnings) == 1:
        payload["warning"] = warnings[0]
        return payload
    payload["warnings"] = warnings
    return payload
