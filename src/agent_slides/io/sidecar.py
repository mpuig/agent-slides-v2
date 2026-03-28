"""Helpers for reading and mutating sidecar deck JSON files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, TypeVar
from uuid import uuid4

from pydantic import ValidationError

from agent_slides.errors import (
    AgentSlidesError,
    FILE_EXISTS,
    FILE_NOT_FOUND,
    REVISION_CONFLICT,
    SCHEMA_ERROR,
)
from agent_slides.model import Deck

T = TypeVar("T")


def _format_validation_error(exc: ValidationError) -> str:
    return json.dumps(exc.errors(include_url=False), sort_keys=True)


def _raise_write_error(path: Path, exc: OSError) -> None:
    raise AgentSlidesError(
        SCHEMA_ERROR,
        f"Failed to write deck file {path}: {exc.strerror or str(exc)}",
    ) from exc


def _write_atomic(path: Path, deck: Deck) -> None:
    tmp_path = Path(f"{path}.tmp")
    payload = f"{deck.model_dump_json(indent=2)}\n"

    try:
        tmp_path.write_text(payload, encoding="utf-8")
        os.rename(tmp_path, path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        _raise_write_error(path, exc)


def read_deck(path: str) -> Deck:
    """Load, parse, and validate a sidecar deck file."""

    deck_path = Path(path)

    try:
        payload = deck_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Deck file not found: {deck_path}") from exc

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON in {deck_path}: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    try:
        return Deck.model_validate(raw)
    except ValidationError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid deck structure in {deck_path}: {_format_validation_error(exc)}",
        ) from exc


def write_deck(path: str, deck: Deck, expected_revision: int) -> None:
    """Persist a deck with an optimistic-lock revision check."""

    deck_path = Path(path)
    current = read_deck(str(deck_path))
    if current.revision != expected_revision:
        raise AgentSlidesError(
            REVISION_CONFLICT,
            f"Revision conflict for {deck_path}: expected {expected_revision}, found {current.revision}",
        )

    _write_atomic(deck_path, deck)


def mutate_deck(path: str, fn: Callable[[Deck], T]) -> tuple[Deck, T]:
    """Run the shared read-mutate-reflow-lock-write pipeline."""

    from agent_slides.engine.reflow import reflow_deck

    deck = read_deck(path)
    expected_revision = deck.revision
    result = fn(deck)
    deck.bump_revision()
    reflow_deck(deck)
    write_deck(path, deck, expected_revision)
    return deck, result


def init_deck(path: str, theme: str, design_rules: str, force: bool) -> Deck:
    """Create a new sidecar deck file."""

    deck_path = Path(path)
    if deck_path.exists() and not force:
        raise AgentSlidesError(FILE_EXISTS, f"Deck file already exists: {deck_path}")

    deck = Deck(
        deck_id=str(uuid4()),
        revision=0,
        theme=theme,
        design_rules=design_rules,
    )
    _write_atomic(deck_path, deck)
    return deck
