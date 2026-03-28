"""Helpers for resolving deck-referenced image assets."""

from __future__ import annotations

from pathlib import Path

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND


def resolve_image_path(image_path: str, *, base_dir: str | Path | None = None) -> Path:
    """Resolve an image path relative to a deck location and ensure it exists."""

    candidate = Path(image_path).expanduser()
    if base_dir is not None:
        asset_root = Path(base_dir).expanduser().resolve()
        if candidate.is_absolute():
            raise AgentSlidesError(FILE_NOT_FOUND, "Path traversal not allowed")

        resolved = (asset_root / candidate).resolve()
        if not resolved.is_relative_to(asset_root):
            raise AgentSlidesError(FILE_NOT_FOUND, "Path traversal not allowed")
    else:
        if not candidate.is_absolute():
            candidate = Path(".").expanduser() / candidate
        resolved = candidate.resolve()

    if not resolved.is_file():
        raise AgentSlidesError(FILE_NOT_FOUND, f"Image file not found: {resolved}")
    return resolved
