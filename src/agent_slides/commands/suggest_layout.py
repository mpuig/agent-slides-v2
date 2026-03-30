"""CLI command for built-in layout recommendations."""

from __future__ import annotations

import json
from pathlib import Path

import click
from pydantic import ValidationError

from agent_slides.engine.layout_suggestions import (
    serialize_suggestions,
    suggest_layouts,
)
from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR
from agent_slides.model import NodeContent


def _read_content_arg(content_arg: str) -> tuple[object, str]:
    if content_arg.startswith("@"):
        path = Path(content_arg[1:])
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AgentSlidesError(
                FILE_NOT_FOUND, f"Content file not found: {path}"
            ) from exc
        source = str(path)
    else:
        raw = content_arg
        source = "`--content`"

    try:
        return json.loads(raw), source
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR, f"Content JSON is not valid: {source}"
        ) from exc


def _parse_content(content_arg: str) -> NodeContent:
    payload, source = _read_content_arg(content_arg)
    if isinstance(payload, str):
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Content JSON must describe structured blocks, not a string: {source}",
        )

    try:
        return NodeContent.model_validate(payload)
    except ValidationError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Content JSON does not match the NodeContent schema: {source}",
        ) from exc


@click.command("suggest-layout")
@click.option("--content", "content_arg", required=True)
@click.option("--image-count", default=0, type=click.IntRange(min=0))
def suggest_layout_command(content_arg: str, image_count: int) -> None:
    """Recommend built-in layouts for structured text content."""

    content = _parse_content(content_arg)
    suggestions = suggest_layouts(content, image_count=image_count, limit=3)
    click.echo(
        json.dumps(
            {"ok": True, "data": {"suggestions": serialize_suggestions(suggestions)}}
        )
    )
