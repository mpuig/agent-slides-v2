"""CLI entry point for agent-slides."""

from __future__ import annotations

import json

import click

from agent_slides import __version__
from agent_slides.commands.batch import batch
from agent_slides.commands.build import build_command
from agent_slides.commands.chart import chart
from agent_slides.commands.contract import contract_command
from agent_slides.commands.icon import icon
from agent_slides.commands.info import info_command
from agent_slides.commands.inspect_cmd import inspect_command
from agent_slides.commands.init import init_command
from agent_slides.commands.learn import learn_command
from agent_slides.commands.pattern import pattern
from agent_slides.commands.preview import preview_command
from agent_slides.commands.review import review_command
from agent_slides.commands.shape import shape
from agent_slides.commands.slide import slide
from agent_slides.commands.slot import slot
from agent_slides.commands.suggest_layout import suggest_layout_command
from agent_slides.commands.table import table
from agent_slides.commands.theme import theme
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
cli.add_command(chart)
cli.add_command(contract_command)
cli.add_command(icon)
cli.add_command(init_command)
cli.add_command(preview_command)
cli.add_command(review_command)
cli.add_command(chart)
cli.add_command(shape)
cli.add_command(slide)
cli.add_command(slot)
cli.add_command(table)
cli.add_command(theme)
cli.add_command(info_command)
cli.add_command(learn_command)
cli.add_command(pattern)
cli.add_command(inspect_command)
cli.add_command(build_command)
cli.add_command(suggest_layout_command, name="suggest-layout")
cli.add_command(preview_command, name="preview")
cli.add_command(validate_command, name="validate")
cli.add_command(info_command, name="info")
cli.add_command(inspect_command, name="inspect")
cli.add_command(build_command, name="build")
cli.add_command(review_command, name="review")
