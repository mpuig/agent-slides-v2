from __future__ import annotations

import json

import click
from click.testing import CliRunner

from agent_slides import __version__
from agent_slides.cli import AgentSlidesGroup, cli
from agent_slides.errors import (
    AgentSlidesError,
    FILE_EXISTS,
    FILE_NOT_FOUND,
    IMAGE_NOT_SUPPORTED,
    INVALID_LAYOUT,
    INVALID_NODE,
    INVALID_SLIDE,
    INVALID_SLOT,
    OVERFLOW,
    REVISION_CONFLICT,
    SCHEMA_ERROR,
    SLOT_OCCUPIED,
    UNBOUND_NODES,
)


def test_package_version_is_importable() -> None:
    assert __version__ == "0.1.0"


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Agent Slides command line interface." in result.output


def test_cli_version_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "agent-slides, version 0.1.0" in result.output


def test_agent_slides_error_is_rendered_as_json_on_stderr() -> None:
    @click.group(cls=AgentSlidesGroup, invoke_without_command=True)
    def failing_cli() -> None:
        raise AgentSlidesError(INVALID_LAYOUT, "Layout is invalid.")

    runner = CliRunner()
    result = runner.invoke(failing_cli, [])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": INVALID_LAYOUT,
            "message": "Layout is invalid.",
        },
    }


def test_all_error_codes_are_defined() -> None:
    assert {
        INVALID_SLIDE,
        INVALID_SLOT,
        INVALID_LAYOUT,
        INVALID_NODE,
        FILE_NOT_FOUND,
        SCHEMA_ERROR,
        OVERFLOW,
        UNBOUND_NODES,
        IMAGE_NOT_SUPPORTED,
        REVISION_CONFLICT,
        SLOT_OCCUPIED,
        FILE_EXISTS,
    } == {
        "INVALID_SLIDE",
        "INVALID_SLOT",
        "INVALID_LAYOUT",
        "INVALID_NODE",
        "FILE_NOT_FOUND",
        "SCHEMA_ERROR",
        "OVERFLOW",
        "UNBOUND_NODES",
        "IMAGE_NOT_SUPPORTED",
        "REVISION_CONFLICT",
        "SLOT_OCCUPIED",
        "FILE_EXISTS",
    }
