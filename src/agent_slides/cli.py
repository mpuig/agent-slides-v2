"""CLI entry point for agent-slides."""

from __future__ import annotations

import json

import click

from agent_slides import __version__
from agent_slides.commands.slot import slot
from agent_slides.errors import AgentSlidesError


def _emit_error(exc: AgentSlidesError) -> None:
    payload = {
        "ok": False,
        "error": {
            "code": exc.code,
            "message": exc.message,
        },
    }
    click.echo(json.dumps(payload), err=True)


class AgentSlidesGroup(click.Group):
    """Click group with uniform JSON error output for domain errors."""

    def main(self, *args: object, **kwargs: object) -> object:
        try:
            return super().main(*args, **kwargs)
        except AgentSlidesError as exc:
            _emit_error(exc)
            raise SystemExit(1) from exc


@click.group(cls=AgentSlidesGroup)
@click.version_option(version=__version__, prog_name="agent-slides")
def cli() -> None:
    """Agent Slides command line interface."""


cli.add_command(slot)
