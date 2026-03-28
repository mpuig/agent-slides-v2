"""I/O helpers package."""

from agent_slides.io.sidecar import (
    computed_sidecar_path,
    init_deck,
    mutate_deck,
    read_computed_deck,
    read_deck,
    resolve_manifest_path,
    write_computed_deck,
    write_deck,
)
from agent_slides.io.template_reader import read_template_manifest
from agent_slides.io.pptx_writer import render_text_node, write_pptx

__all__ = [
    "computed_sidecar_path",
    "init_deck",
    "mutate_deck",
    "read_computed_deck",
    "read_deck",
    "read_template_manifest",
    "render_text_node",
    "resolve_manifest_path",
    "write_computed_deck",
    "write_deck",
    "write_pptx",
]
