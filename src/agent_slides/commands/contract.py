"""CLI command for emitting the canonical agent contract."""

from __future__ import annotations

import json

import click

from agent_slides.contract import build_contract


@click.command("contract")
def contract_command() -> None:
    """Emit the canonical machine-readable agent contract as JSON."""

    click.echo(json.dumps(build_contract(), indent=2, sort_keys=True))
