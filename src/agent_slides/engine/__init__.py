"""Layout and render engine package."""

from agent_slides.engine.text_fit import fit_text
from .validator import validate_deck, validate_slide

__all__ = ["fit_text", "validate_deck", "validate_slide"]
