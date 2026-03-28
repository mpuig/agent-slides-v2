"""Slide collection commands."""

from __future__ import annotations

import json

import click

from agent_slides.commands.mutations import apply_mutation
from agent_slides.commands.warnings import attach_layout_fallback_warning
from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR, UNBOUND_NODES
from agent_slides.io import mutate_deck
from agent_slides.model import Deck, NodeContent
from agent_slides.model.layout_provider import LayoutProvider


def _emit_json(payload: dict[str, object], *, err: bool = False) -> None:
    click.echo(json.dumps(payload), err=err)


def _emit_warning(slide_id: str, unbound_nodes: list[str]) -> None:
    if not unbound_nodes:
        return

    _emit_json(
        {
            "ok": True,
            "warning": {
                "code": UNBOUND_NODES,
                "message": f"{len(unbound_nodes)} node(s) became unbound during slot rebinding.",
            },
            "data": {
                "slide_id": slide_id,
                "unbound_nodes": unbound_nodes,
            },
        },
        err=True,
    )
@click.group()
def slide() -> None:
    """Manage deck slides."""


def _parse_content_json(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON for '--content': {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    try:
        return NodeContent.model_validate(payload).model_dump(mode="json")
    except Exception as exc:
        raise AgentSlidesError(SCHEMA_ERROR, "Argument '--content' must be valid structured text") from exc


@slide.command("add")
@click.argument("path")
@click.option("--layout", "layout_name")
@click.option("--auto-layout", is_flag=True, default=False)
@click.option("--content", "content_json")
@click.option("--image-count", default=0, type=int, show_default=True)
def add_slide_command(
    path: str,
    layout_name: str | None,
    auto_layout: bool,
    content_json: str | None,
    image_count: int,
) -> None:
    """Append a slide using a named layout."""

    if auto_layout and layout_name:
        raise AgentSlidesError(SCHEMA_ERROR, "`--auto-layout` and `--layout` are mutually exclusive.")
    if auto_layout:
        if content_json is None:
            raise AgentSlidesError(SCHEMA_ERROR, "`--content` is required when using `--auto-layout`.")
        mutation_args: dict[str, object] = {
            "auto_layout": True,
            "content": _parse_content_json(content_json),
            "image_count": image_count,
        }
    else:
        if layout_name is None:
            raise AgentSlidesError(SCHEMA_ERROR, "`--layout` is required unless `--auto-layout` is set.")
        if content_json is not None:
            raise AgentSlidesError(SCHEMA_ERROR, "`--content` requires `--auto-layout`.")
        if image_count != 0:
            raise AgentSlidesError(SCHEMA_ERROR, "`--image-count` requires `--auto-layout`.")
        mutation_args = {"layout": layout_name}

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "slide_add", mutation_args, provider)

    deck, result = mutate_deck(path, mutate)
    _emit_json(attach_layout_fallback_warning({"ok": True, "data": result}, deck))


@slide.command("remove")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
def remove_slide_command(path: str, slide_ref: str) -> None:
    """Remove a slide by index or slide_id."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(deck, "slide_remove", {"slide": slide_ref}, provider)

    deck, result = mutate_deck(path, mutate)
    _emit_json(attach_layout_fallback_warning({"ok": True, "data": result}, deck))


@slide.command("set-layout")
@click.argument("path")
@click.option("--slide", "slide_ref", required=True)
@click.option("--layout", "layout_name", required=True)
def set_slide_layout_command(path: str, slide_ref: str, layout_name: str) -> None:
    """Change a slide layout and rebind its slot-bound nodes."""

    def mutate(deck: Deck, provider: LayoutProvider) -> dict[str, object]:
        return apply_mutation(
            deck,
            "slide_set_layout",
            {
                "slide": slide_ref,
                "layout": layout_name,
            },
            provider,
        )

    deck, result = mutate_deck(path, mutate)
    _emit_warning(result["slide_id"], result["unbound_nodes"])
    _emit_json(
        attach_layout_fallback_warning(
            {"ok": True, "data": result},
            deck,
            slide_ids=[str(result["slide_id"])],
        )
    )
