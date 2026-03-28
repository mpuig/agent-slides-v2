"""I/O helpers package."""

from agent_slides.io.sidecar import init_deck, mutate_deck, read_deck, write_deck
from agent_slides.io.pptx_writer import render_text_node, write_pptx

__all__ = [
    "init_deck",
    "mutate_deck",
    "read_deck",
    "render_text_node",
    "write_deck",
    "write_pptx",
]
