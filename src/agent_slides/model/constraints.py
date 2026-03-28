"""Constraint models emitted by validation."""

from typing import Literal

from pydantic import BaseModel


class Constraint(BaseModel):
    """A single validator finding tied to a slide or node."""

    code: str
    severity: Literal["error", "warning"]
    message: str
    slide_id: str | None = None
    node_id: str | None = None
