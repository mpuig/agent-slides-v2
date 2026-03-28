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
REVISION_CONFLICT = "REVISION_CONFLICT"
SLOT_OCCUPIED = "SLOT_OCCUPIED"
FILE_EXISTS = "FILE_EXISTS"


class AgentSlidesError(Exception):
    """Single application error type used across the CLI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


__all__ = [
    "AgentSlidesError",
    "FILE_EXISTS",
    "FILE_NOT_FOUND",
    "IMAGE_NOT_SUPPORTED",
    "INVALID_LAYOUT",
    "INVALID_SLIDE",
    "INVALID_SLOT",
    "OVERFLOW",
    "REVISION_CONFLICT",
    "SCHEMA_ERROR",
    "SLOT_OCCUPIED",
    "UNBOUND_NODES",
]
