"""Slot content commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.ops import parse_slide_ref, set_slot_text


@click.group()
def slot() -> None:
    """Manage slot-bound content."""


@slot.command("set")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--slot", "slot_name", required=True)
@click.option("--text", required=True)
def set_slot_command(path: str, slide_ref: str, slot_name: str, text: str) -> None:
    """Set text content for a slot on a slide."""

    result = set_slot_text(path, parse_slide_ref(slide_ref), slot_name, text)
    click.echo(json.dumps({"ok": True, "data": result}))
