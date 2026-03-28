"""Shared error definitions for agent-slides."""

from __future__ import annotations

INVALID_SLIDE = "INVALID_SLIDE"
INVALID_SLOT = "INVALID_SLOT"
INVALID_LAYOUT = "INVALID_LAYOUT"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
SCHEMA_ERROR = "SCHEMA_ERROR"
OVERFLOW = "OVERFLOW"
UNBOUND_NODES = "UNBOUND_NODES"
IMAGE_NOT_SUPPORTED = "IMAGE_NOT_SUPPORTED"
INVALID_CHART_TYPE = "INVALID_CHART_TYPE"
INVALID_NODE_TYPE = "INVALID_NODE_TYPE"
REVISION_CONFLICT = "REVISION_CONFLICT"
SLOT_OCCUPIED = "SLOT_OCCUPIED"
FILE_EXISTS = "FILE_EXISTS"
TEMPLATE_CHANGED = "TEMPLATE_CHANGED"
CHART_DATA_ERROR = "CHART_DATA_ERROR"
THEME_INVALID = "THEME_INVALID"
THEME_NOT_FOUND = "THEME_NOT_FOUND"
THEME_ROLE_NOT_FOUND = "THEME_ROLE_NOT_FOUND"
INVALID_TOOL_INPUT = "INVALID_TOOL_INPUT"
INVALID_TOOL_NAME = "INVALID_TOOL_NAME"
INVALID_ICON = "INVALID_ICON"


class AgentSlidesError(Exception):
    """Single application error type used across the CLI."""

    def __init__(self, code: str, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        return self.message

__all__ = [
    "AgentSlidesError",
    "CHART_DATA_ERROR",
    "FILE_EXISTS",
    "FILE_NOT_FOUND",
    "IMAGE_NOT_SUPPORTED",
    "INVALID_CHART_TYPE",
    "INVALID_ICON",
    "INVALID_LAYOUT",
    "INVALID_NODE_TYPE",
    "INVALID_SLIDE",
    "INVALID_SLOT",
    "INVALID_TOOL_INPUT",
    "INVALID_TOOL_NAME",
    "OVERFLOW",
    "REVISION_CONFLICT",
    "SCHEMA_ERROR",
    "SLOT_OCCUPIED",
    "TEMPLATE_CHANGED",
    "THEME_INVALID",
    "THEME_NOT_FOUND",
    "THEME_ROLE_NOT_FOUND",
    "UNBOUND_NODES",
]
