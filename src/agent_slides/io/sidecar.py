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
from agent_slides.model import ComputedDeck, Deck

T = TypeVar("T")


def _format_validation_error(exc: ValidationError) -> str:
    return json.dumps(exc.errors(include_url=False), sort_keys=True)


def _raise_write_error(path: Path, exc: OSError) -> None:
    raise AgentSlidesError(
        SCHEMA_ERROR,
        f"Failed to write deck file {path}: {exc.strerror or str(exc)}",
    ) from exc


def _stage_atomic_write(path: Path, payload: str) -> Path:
    tmp_path = Path(f"{path}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    return tmp_path


def _cleanup_tmp_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _commit_staged_writes(staged_paths: list[tuple[Path, Path]]) -> None:
    written_tmp_paths: list[Path] = []

    try:
        for tmp_path, path in staged_paths:
            written_tmp_paths.append(tmp_path)
            os.rename(tmp_path, path)
    except OSError as exc:
        _cleanup_tmp_files(written_tmp_paths)
        pending = [tmp_path for tmp_path, _ in staged_paths if tmp_path not in written_tmp_paths]
        _cleanup_tmp_files(pending)
        _raise_write_error(path, exc)


def _serialize_deck_payload(deck: Deck) -> str:
    payload = deck.model_dump(mode="json", by_alias=True)
    for slide in payload["slides"]:
        slide.pop("computed", None)
    return f"{json.dumps(payload, indent=2)}\n"


def _serialize_computed_payload(deck: Deck) -> str:
    return f"{ComputedDeck.from_deck(deck).model_dump_json(indent=2)}\n"


def _write_bundle_atomic(path: Path, deck: Deck) -> None:
    computed_path = computed_sidecar_path(path)
    staged_paths: list[tuple[Path, Path]] = []

    try:
        staged_paths.append((_stage_atomic_write(path, _serialize_deck_payload(deck)), path))
        staged_paths.append(
            (_stage_atomic_write(computed_path, _serialize_computed_payload(deck)), computed_path)
        )
    except OSError as exc:
        _cleanup_tmp_files([tmp_path for tmp_path, _ in staged_paths])
        _raise_write_error(path, exc)

    _commit_staged_writes(staged_paths)


def computed_sidecar_path(path: str | Path) -> Path:
    deck_path = Path(path)
    return deck_path.with_name(f"{deck_path.stem}.computed{deck_path.suffix}")


def _parse_json_file(path: Path) -> object:
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Deck file not found: {path}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid JSON in {path}: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc


def _read_computed_deck_optional(path: Path) -> ComputedDeck | None:
    try:
        raw = _parse_json_file(path)
    except AgentSlidesError as exc:
        if exc.code == FILE_NOT_FOUND:
            return None
        raise

    try:
        return ComputedDeck.model_validate(raw)
    except ValidationError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid computed deck structure in {path}: {_format_validation_error(exc)}",
        ) from exc


def read_deck(path: str) -> Deck:
    """Load, parse, and validate a sidecar deck file."""

    deck_path = Path(path)
    raw = _parse_json_file(deck_path)

    try:
        deck = Deck.model_validate(raw)
    except ValidationError as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Invalid deck structure in {deck_path}: {_format_validation_error(exc)}",
        ) from exc

    computed_deck = _read_computed_deck_optional(computed_sidecar_path(deck_path))
    if computed_deck is not None:
        computed_deck.apply_to_deck(deck)

    return deck


def read_computed_deck(path: str) -> ComputedDeck:
    """Load, parse, and validate a computed deck sidecar."""

    computed_path = computed_sidecar_path(path)
    computed_deck = _read_computed_deck_optional(computed_path)
    if computed_deck is None:
        raise AgentSlidesError(FILE_NOT_FOUND, f"Deck file not found: {computed_path}")
    return computed_deck


def write_computed_deck(path: str, deck: Deck) -> None:
    """Persist just the computed sidecar for an already-loaded deck."""

    computed_path = computed_sidecar_path(path)

    try:
        staged = _stage_atomic_write(computed_path, _serialize_computed_payload(deck))
    except OSError as exc:
        _raise_write_error(computed_path, exc)

    _commit_staged_writes([(staged, computed_path)])


def write_deck(path: str, deck: Deck, expected_revision: int) -> None:
    """Persist a deck with an optimistic-lock revision check."""

    deck_path = Path(path)
    current = read_deck(str(deck_path))
    if current.revision != expected_revision:
        raise AgentSlidesError(
            REVISION_CONFLICT,
            f"Revision conflict for {deck_path}: expected {expected_revision}, found {current.revision}",
        )

    _write_bundle_atomic(deck_path, deck)


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
    _write_bundle_atomic(deck_path, deck)
    return deck
