from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from click.testing import CliRunner

from agent_slides.cli import cli
from agent_slides.errors import FILE_EXISTS, FILE_NOT_FOUND, THEME_NOT_FOUND


def read_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_init_creates_valid_deck_file_and_reports_success_json(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"

    result = runner.invoke(cli, ["init", str(deck_path)])

    assert result.exit_code == 0
    response = json.loads(result.output)
    payload = read_payload(deck_path)

    assert response["ok"] is True
    assert response["data"] == {
        "deck_id": payload["deck_id"],
        "theme": "default",
        "design_rules": "default",
    }
    assert UUID(str(payload["deck_id"]))
    assert payload["revision"] == 0
    assert payload["slides"] == []
    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"
    assert payload["version"] == 1
    assert payload["_counters"] == {"slides": 0, "nodes": 0}


def test_init_applies_explicit_theme_and_rules_options(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"

    result = runner.invoke(
        cli,
        ["init", str(deck_path), "--theme", "default", "--rules", "default"],
    )

    assert result.exit_code == 0
    payload = read_payload(deck_path)

    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"


def test_init_returns_file_exists_error_when_target_exists(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(cli, ["init", str(deck_path)])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_EXISTS,
            "message": f"Deck file already exists: {deck_path}",
        },
    }


def test_init_force_overwrites_existing_file(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(
        json.dumps({"deck_id": "old", "revision": 9, "slides": ["stale"]}),
        encoding="utf-8",
    )

    result = runner.invoke(cli, ["init", str(deck_path), "--force"])

    assert result.exit_code == 0
    payload = read_payload(deck_path)

    assert payload["revision"] == 0
    assert payload["slides"] == []
    assert payload["theme"] == "default"
    assert payload["design_rules"] == "default"
    assert payload["deck_id"] != "old"


def test_init_returns_theme_validation_error_for_invalid_theme(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"

    result = runner.invoke(cli, ["init", str(deck_path), "--theme", "missing"])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": THEME_NOT_FOUND,
            "message": "Theme 'missing' was not found.",
        },
    }
    assert not deck_path.exists()


def test_init_returns_rules_validation_error_for_invalid_rules(tmp_path: Path) -> None:
    runner = CliRunner()
    deck_path = tmp_path / "deck.json"

    result = runner.invoke(cli, ["init", str(deck_path), "--rules", "missing"])

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {
        "ok": False,
        "error": {
            "code": FILE_NOT_FOUND,
            "message": "Design rules profile 'missing' was not found.",
        },
    }
    assert not deck_path.exists()
