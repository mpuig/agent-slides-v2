"""Layout provider protocol and built-in implementation."""

from __future__ import annotations

from typing import Protocol

from agent_slides.model.layouts import get_layout, get_slot_names, get_text_fitting, list_layouts
from agent_slides.model.template_layouts import TemplateLayoutRegistry
from agent_slides.model.types import LayoutDef, TextFitting

_LAYOUT_VARIANTS: dict[str, tuple[str, ...]] = {
    "comparison": ("two_col", "title_content"),
    "gallery": ("image_left", "title_content"),
    "hero_image": ("image_left", "image_right"),
    "image_left": ("image_right", "title_content"),
    "image_right": ("image_left", "title_content"),
    "three_col": ("two_col", "title_content"),
    "title": ("title_content",),
    "title_content": ("two_col",),
    "two_col": ("title_content",),
}


class LayoutProvider(Protocol):
    def get_layout(self, slug: str) -> LayoutDef: ...

    def list_layouts(self) -> list[str]: ...

    def get_slot_names(self, slug: str) -> list[str]: ...

    def get_text_fitting(self, slug: str, role: str) -> TextFitting: ...

    def get_variants(self, slug: str) -> list[LayoutDef]: ...


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

    def get_variants(self, slug: str) -> list[LayoutDef]:
        return [get_layout(name) for name in _LAYOUT_VARIANTS.get(slug, ())]


def resolve_layout_provider(template_manifest: str | None) -> LayoutProvider:
    """Resolve the active layout provider for a deck."""

    if template_manifest is None:
        return BuiltinLayoutProvider()
    if not isinstance(template_manifest, str) or not template_manifest.strip():
        raise TypeError("template_manifest must be a non-empty string when provided")
    return TemplateLayoutRegistry(template_manifest)
