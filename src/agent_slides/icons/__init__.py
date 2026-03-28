"""Built-in icon registry and SVG path helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

from agent_slides.errors import AgentSlidesError, INVALID_ICON, SCHEMA_ERROR

ICON_VIEWBOX = 24.0
_HEX_COLOR_RE = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PATH_TOKEN_RE = re.compile(r"[MLHVZ]|-?(?:\d+(?:\.\d*)?|\.\d+)")


@lru_cache(maxsize=1)
def _icon_index() -> dict[str, str]:
    payload = resources.files("agent_slides.icons").joinpath("library.json").read_text(encoding="utf-8")
    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise AgentSlidesError(SCHEMA_ERROR, "Built-in icon library is invalid")
    return {str(name): str(path) for name, path in raw.items()}


def list_icons() -> list[str]:
    """Return the names of all built-in icons."""

    return sorted(_icon_index())


def has_icon(name: str) -> bool:
    """Return whether a named built-in icon exists."""

    return name.strip() in _icon_index()


def require_icon(name: str) -> str:
    """Return the SVG path for a named icon or raise a domain error."""

    normalized = name.strip()
    path = _icon_index().get(normalized)
    if path is None:
        raise AgentSlidesError(
            INVALID_ICON,
            f"Unknown icon {name!r}",
            details={"icon": normalized, "valid_icons": list_icons()},
        )
    return path


def normalize_hex_color(value: object, *, field_name: str = "color") -> str:
    """Normalize a hex color to #RRGGBB."""

    if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value.strip()):
        raise AgentSlidesError(SCHEMA_ERROR, f"Argument '{field_name}' must be a hex color like '#1A73E8'")

    normalized = value.strip().lstrip("#").upper()
    if len(normalized) == 3:
        normalized = "".join(channel * 2 for channel in normalized)
    return f"#{normalized}"


def svg_path_subpaths(path_data: str) -> list[list[tuple[float, float]]]:
    """Parse a simple absolute SVG path string into closed/open subpaths."""

    tokens = _PATH_TOKEN_RE.findall(path_data)
    if not tokens:
        return []

    index = 0
    command = ""
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    active: list[tuple[float, float]] = []
    subpaths: list[list[tuple[float, float]]] = []

    def flush() -> None:
        nonlocal active
        if active:
            subpaths.append(active)
            active = []

    def take_number() -> float:
        nonlocal index
        if index >= len(tokens):
            raise AgentSlidesError(SCHEMA_ERROR, "Built-in icon library contains malformed SVG path data")
        token = tokens[index]
        index += 1
        if token in {"M", "L", "H", "V", "Z"}:
            raise AgentSlidesError(SCHEMA_ERROR, "Built-in icon library contains malformed SVG path data")
        return float(token)

    while index < len(tokens):
        token = tokens[index]
        if token in {"M", "L", "H", "V", "Z"}:
            command = token
            index += 1
            if command == "Z":
                if active and active[0] != active[-1]:
                    active.append(active[0])
                flush()
                current = start
                continue
        elif not command:
            raise AgentSlidesError(SCHEMA_ERROR, "Built-in icon library contains malformed SVG path data")

        if command == "M":
            x = take_number()
            y = take_number()
            flush()
            current = (x, y)
            start = current
            active = [current]
            command = "L"
            continue

        if command == "L":
            x = take_number()
            y = take_number()
            current = (x, y)
            active.append(current)
            continue

        if command == "H":
            current = (take_number(), current[1])
            active.append(current)
            continue

        if command == "V":
            current = (current[0], take_number())
            active.append(current)
            continue

        raise AgentSlidesError(SCHEMA_ERROR, "Built-in icon library contains unsupported SVG path data")

    flush()
    return [subpath for subpath in subpaths if len(subpath) >= 2]


__all__ = [
    "ICON_VIEWBOX",
    "has_icon",
    "list_icons",
    "normalize_hex_color",
    "require_icon",
    "svg_path_subpaths",
]
