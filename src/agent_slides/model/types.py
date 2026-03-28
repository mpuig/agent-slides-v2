"""Core model value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    primary: str
    secondary: str
    accent: str
    background: str
    text: str
    heading_text: str
    subtle_text: str


@dataclass(frozen=True)
class ThemeFonts:
    heading: str
    body: str


@dataclass(frozen=True)
class ThemeSpacing:
    base_unit: int
    margin: int
    gutter: int


@dataclass(frozen=True)
class Theme:
    name: str
    colors: ThemeColors
    fonts: ThemeFonts
    spacing: ThemeSpacing
