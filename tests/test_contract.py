from __future__ import annotations

import json

import click
from click.testing import CliRunner

from agent_slides.cli import cli
from agent_slides.commands.mutations import SUPPORTED_MUTATION_COMMANDS
from agent_slides.contract import (
    COMMAND_CONTRACTS,
    LEGACY_ORCHESTRATOR_PROFILE,
    MUTATION_COMMAND_NAMES,
    PREVIEW_CHAT_PROFILE,
    TOOL_PROFILES,
    build_contract,
    get_tool_definitions,
)


def _leaf_commands(command: click.Command, prefix: tuple[str, ...] = ()) -> set[str]:
    if not hasattr(command, "commands"):
        return {" ".join(prefix)}

    names: set[str] = set()
    for name, subcommand in getattr(command, "commands").items():
        names |= _leaf_commands(subcommand, (*prefix, name))
    return names


def test_contract_command_emits_canonical_registry() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["contract"])

    assert result.exit_code == 0
    assert json.loads(result.output) == build_contract()


def test_contract_command_registry_matches_cli_leaf_commands() -> None:
    assert {payload["cli_command"] for payload in COMMAND_CONTRACTS.values()} == _leaf_commands(cli)


def test_contract_mutation_registry_matches_supported_mutations() -> None:
    assert set(MUTATION_COMMAND_NAMES) == SUPPORTED_MUTATION_COMMANDS


def test_contract_tool_profiles_emit_shared_definitions() -> None:
    legacy_tools = get_tool_definitions(profile=LEGACY_ORCHESTRATOR_PROFILE)
    preview_tools = get_tool_definitions(profile=PREVIEW_CHAT_PROFILE)

    assert [tool["name"] for tool in legacy_tools] == TOOL_PROFILES[LEGACY_ORCHESTRATOR_PROFILE]
    assert [tool["name"] for tool in preview_tools] == TOOL_PROFILES[PREVIEW_CHAT_PROFILE]
    assert any(tool["name"] == "build" and "output_path" in tool["input_schema"]["properties"] for tool in legacy_tools)
    assert any(tool["name"] == "get_deck_info" for tool in preview_tools)
