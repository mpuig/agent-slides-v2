"""Layout provider protocol and built-in implementation."""

from __future__ import annotations

from typing import Protocol

from agent_slides.model.layouts import get_layout, get_slot_names, get_text_fitting, list_layouts
from agent_slides.model.types import LayoutDef, TextFitting


class LayoutProvider(Protocol):
    def get_layout(self, slug: str) -> LayoutDef: ...

    def list_layouts(self) -> list[str]: ...

    def get_slot_names(self, slug: str) -> list[str]: ...

    def get_text_fitting(self, slug: str, role: str) -> TextFitting: ...


class BuiltinLayoutProvider:
    """Wrap the built-in layout registry behind the LayoutProvider protocol."""

    def get_layout(self, slug: str) -> LayoutDef:
        return get_layout(slug)

    def list_layouts(self) -> list[str]:
        return list_layouts()

    def get_slot_names(self, slug: str) -> list[str]:
        return get_slot_names(slug)

    def get_text_fitting(self, slug: str, role: str) -> TextFitting:
        return get_text_fitting(slug, role)


def resolve_layout_provider(template_manifest: object | None) -> LayoutProvider:
    """Resolve the active layout provider for a deck."""

    # Template-backed providers land in a follow-up issue. Decks without a template
    # manifest, which is every current deck, keep using the built-in registry.
    if template_manifest is None:
        return BuiltinLayoutProvider()
    return BuiltinLayoutProvider()
