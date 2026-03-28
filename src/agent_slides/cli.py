"""CLI entry point for agent-slides."""

from __future__ import annotations

import json

import click

from agent_slides import __version__
from agent_slides.commands.batch import batch
from agent_slides.commands.build import build_command
from agent_slides.commands.info import info_command
from agent_slides.commands.init import init_command
from agent_slides.commands.preview import preview_command
from agent_slides.commands.slide import slide
from agent_slides.commands.slot import slot
from agent_slides.commands.validate_cmd import validate_command
from agent_slides.errors import AgentSlidesError


def _emit_error(exc: AgentSlidesError) -> None:
    error = {
        "code": exc.code,
        "message": exc.message,
    }
    error.update(exc.details)
    payload = {
        "ok": False,
        "error": error,
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


cli.add_command(batch)
cli.add_command(init_command)
cli.add_command(preview_command)
cli.add_command(slide)
cli.add_command(slot)
cli.add_command(info_command)
cli.add_command(build_command)
cli.add_command(validate_command, name="validate")
cli.add_command(info_command, name="info")
cli.add_command(build_command, name="build")
