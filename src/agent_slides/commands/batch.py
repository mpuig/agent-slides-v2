"""Batch CLI command for atomic deck mutations."""

from __future__ import annotations

import json
from typing import Any

import click

from agent_slides.commands.mutations import SUPPORTED_MUTATION_COMMANDS, apply_mutation
from agent_slides.errors import AgentSlidesError, SCHEMA_ERROR
from agent_slides.io import mutate_deck


def _parse_batch_operations(stdin_payload: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(stdin_payload)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON batch payload: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    if not isinstance(payload, list):
        raise AgentSlidesError(SCHEMA_ERROR, "Batch payload must be a JSON array of operations")

    operations: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AgentSlidesError(SCHEMA_ERROR, f"Operation {index} must be an object")

        command = item.get("command")
        if not isinstance(command, str) or not command.strip():
            raise AgentSlidesError(SCHEMA_ERROR, f"Operation {index} is missing a non-empty 'command'")
        if command not in SUPPORTED_MUTATION_COMMANDS:
            supported = ", ".join(sorted(SUPPORTED_MUTATION_COMMANDS))
            raise AgentSlidesError(
                SCHEMA_ERROR,
                f"Operation {index} uses unsupported command {command!r}. Supported commands: {supported}",
            )

        args = item.get("args", {})
        if not isinstance(args, dict):
            raise AgentSlidesError(SCHEMA_ERROR, f"Operation {index} field 'args' must be an object")

        operations.append({"command": command, "args": args})

    return operations


@click.command("batch")
@click.argument("path", type=click.Path(path_type=str))
def batch(path: str) -> None:
    """Apply multiple deck mutations from JSON stdin in one atomic write."""

    operations = _parse_batch_operations(click.get_text_stream("stdin").read())
    if not operations:
        click.echo(json.dumps({"ok": True, "data": {"operations": 0, "results": []}}))
        return

    def mutate(deck: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, operation in enumerate(operations):
            try:
                results.append(apply_mutation(deck, operation["command"], operation["args"]))
            except AgentSlidesError as exc:
                raise AgentSlidesError(
                    exc.code,
                    exc.message,
                    details={"operation_index": index, **exc.details},
                ) from exc
        return results

    _, results = mutate_deck(path, mutate)
    click.echo(json.dumps({"ok": True, "data": {"operations": len(results), "results": results}}))
