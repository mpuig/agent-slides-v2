"""Reflow entry point.

The real layout engine lands in a later issue. For now the mutation pipeline
needs a stable call site that can be replaced without changing command code.
"""

from __future__ import annotations

from agent_slides.model import Deck


def reflow_deck(deck: Deck) -> None:
    """Stub reflow hook for the shared mutation pipeline."""

    _ = deck
