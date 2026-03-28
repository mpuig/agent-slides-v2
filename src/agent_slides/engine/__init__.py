"""Layout and render engine package."""

from agent_slides.engine.layout_suggestions import LayoutSuggestion, suggest_layouts
from agent_slides.engine.reflow import rebind_slots, reflow_deck
from agent_slides.engine.text_fit import fit_text
from agent_slides.engine.validator import validate_deck, validate_slide

__all__ = [
    "LayoutSuggestion",
    "fit_text",
    "rebind_slots",
    "reflow_deck",
    "suggest_layouts",
    "validate_deck",
    "validate_slide",
]
