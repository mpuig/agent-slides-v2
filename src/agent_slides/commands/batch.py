"""Batch command for applying multiple deck mutations from stdin."""

from __future__ import annotations

import json

import click

from agent_slides.commands.ops import apply_batch


@click.command("batch")
@click.argument("path", type=click.Path(dir_okay=False, path_type=str))
def batch_command(path: str) -> None:
    """Apply a JSON array of operations read from stdin."""

    payload = click.get_text_stream("stdin").read()
    click.echo(json.dumps({"ok": True, "data": {"results": apply_batch(path, payload)}}))
