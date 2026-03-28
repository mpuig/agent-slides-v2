"""Helpers for tracking per-slide preview revisions in computed state."""

from __future__ import annotations

from typing import Any

from agent_slides.model import Slide


def slide_semantic_signature(slide: Slide) -> dict[str, Any]:
    """Return the authoring-state subset used to detect slide changes."""

    return slide.model_dump(mode="json", exclude={"computed", "revision"})


def current_slide_revision(slide: Slide, deck_revision: int) -> int:
    """Return the existing per-slide revision when one is available."""

    if slide.revision > 0 or slide.computed:
        return slide.revision
    return deck_revision


def resolve_slide_revision(
    slide: Slide,
    *,
    deck_revision: int,
    previous_slide_signatures: dict[str, object] | None = None,
) -> int:
    """Reuse the previous slide revision when the slide authoring state is unchanged."""

    if previous_slide_signatures is None:
        return current_slide_revision(slide, deck_revision)

    previous_signature = previous_slide_signatures.get(slide.slide_id)
    if previous_signature == slide_semantic_signature(slide):
        return current_slide_revision(slide, deck_revision)
    return deck_revision
