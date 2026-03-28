"""Helpers for writing deck sidecar JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_slides.errors import AgentSlidesError, FILE_EXISTS, SCHEMA_ERROR


def _initial_deck_payload(theme: str, design_rules: str) -> dict[str, Any]:
    return {
        "version": 1,
        "deck_id": str(uuid4()),
        "revision": 0,
        "theme": theme,
        "design_rules": design_rules,
        "slides": [],
        "_counters": {
            "slides": 0,
            "nodes": 0,
        },
    }


def init_deck(path: str, theme: str, design_rules: str, force: bool) -> dict[str, Any]:
    """Create a new deck JSON file and return the created payload."""

    deck_path = Path(path)
    if deck_path.exists() and not force:
        raise AgentSlidesError(FILE_EXISTS, f"Deck file already exists: {deck_path}")

    payload = _initial_deck_payload(theme, design_rules)

    try:
        deck_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    except OSError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Failed to write deck file {deck_path}: {exc.strerror or str(exc)}",
        ) from exc

    return payload
