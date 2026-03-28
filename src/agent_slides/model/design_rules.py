"""Design-rules models and packaged profile loading."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR

DEFAULT_TYPE_LADDERS = {
    "heading": [36.0, 32.0, 28.0, 24.0],
    "body": [18.0, 16.0, 14.0, 12.0, 10.0],
    "quote": [28.0, 24.0, 20.0, 18.0],
    "attribution": [16.0, 14.0, 12.0, 10.0],
}
HEX_COLOR_DIGITS = frozenset("0123456789abcdefABCDEF")


def _normalize_hex_color(value: str, *, field_name: str) -> str:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6 or any(char not in HEX_COLOR_DIGITS for char in normalized):
        raise ValueError(f"{field_name} must use #RRGGBB or RRGGBB format")
    return f"#{normalized.upper()}"


class ContentLimits(BaseModel):
    """Hard limits for deck content density."""

    max_bullets_per_slide: int
    max_words_per_column: int
    max_slides: int


class FontSizeRange(BaseModel):
    """Allowed font-size range for a text role."""

    min_size: int
    max_size: int


class HierarchyRules(BaseModel):
    """Typography bounds for slide hierarchy."""

    heading: FontSizeRange
    body: FontSizeRange


class OverflowPolicy(BaseModel):
    """Text overflow handling rules."""

    strategy: Literal["shrink", "warn"]
    min_font_size: int


class DeckStructureRules(BaseModel):
    """Recommendations for deck-level structure."""

    recommend_title_slide: bool
    recommend_closing_slide: bool


class LayoutHints(BaseModel):
    """Thresholds used by automatic layout suggestion heuristics."""

    max_bullets_for_single_column: int = 5
    equal_length_threshold: float = 0.4
    short_text_threshold: int = 10


class ConditionalRule(BaseModel):
    """A rule that decorates matching text spans during rendering."""

    pattern: Literal["positive_number", "negative_number", "keyword"]
    color: str
    bold: bool = False
    match: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        return _normalize_hex_color(value, field_name="color")

    @field_validator("match")
    @classmethod
    def validate_match(cls, value: str | None, info) -> str | None:
        if info.data.get("pattern") == "keyword":
            if value is None or not value.strip():
                raise ValueError("keyword rules require a non-empty match value")
            return value.strip()
        return value


class ChartConditionalFormatting(BaseModel):
    positive_color: str = "#1B8A2D"
    negative_color: str = "#D32F2F"
    highlight_color: str = "#C98E48"
    muted_color: str = "#CFC8BD"

    @field_validator("positive_color", "negative_color", "highlight_color", "muted_color")
    @classmethod
    def validate_colors(cls, value: str, info) -> str:
        return _normalize_hex_color(value, field_name=info.field_name)


class TableStatusStyle(BaseModel):
    fill: str
    text: str = "#1F1E1A"
    bold: bool = True

    @field_validator("fill", "text")
    @classmethod
    def validate_colors(cls, value: str, info) -> str:
        return _normalize_hex_color(value, field_name=info.field_name)


class TableConditionalFormatting(BaseModel):
    statuses: dict[str, TableStatusStyle] = Field(
        default_factory=lambda: {
            "complete": TableStatusStyle(fill="#DDF4E4", text="#1B5E20", bold=True),
            "on track": TableStatusStyle(fill="#DDF4E4", text="#1B5E20", bold=True),
            "at risk": TableStatusStyle(fill="#FDE3E3", text="#8B1E1E", bold=True),
            "blocked": TableStatusStyle(fill="#FDE3E3", text="#8B1E1E", bold=True),
            "in progress": TableStatusStyle(fill="#FFF1C7", text="#8A5A00", bold=True),
        }
    )

    @field_validator("statuses")
    @classmethod
    def validate_status_keys(cls, value: dict[str, TableStatusStyle]) -> dict[str, TableStatusStyle]:
        normalized: dict[str, TableStatusStyle] = {}
        for key, style in value.items():
            normalized_key = key.strip().casefold()
            if not normalized_key:
                raise ValueError("table status keys must be non-empty")
            normalized[normalized_key] = style
        return normalized


class ConditionalFormatting(BaseModel):
    color_aliases: dict[str, str] = Field(
        default_factory=lambda: {
            "green": "#1B8A2D",
            "red": "#D32F2F",
            "yellow": "#F2C94C",
            "amber": "#C98E48",
            "gray": "#8F8A81",
            "grey": "#8F8A81",
            "highlight": "#C98E48",
            "muted": "#CFC8BD",
        }
    )
    text_rules: list[ConditionalRule] = Field(
        default_factory=lambda: [
            ConditionalRule(pattern="positive_number", color="#1B8A2D"),
            ConditionalRule(pattern="negative_number", color="#D32F2F"),
        ]
    )
    chart: ChartConditionalFormatting = Field(default_factory=ChartConditionalFormatting)
    table: TableConditionalFormatting = Field(default_factory=TableConditionalFormatting)

    @field_validator("color_aliases")
    @classmethod
    def validate_color_aliases(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, color in value.items():
            normalized_key = key.strip().casefold()
            if not normalized_key:
                raise ValueError("color aliases must use non-empty names")
            normalized[normalized_key] = _normalize_hex_color(color, field_name=f"color_aliases.{key}")
        return normalized


class DesignRules(BaseModel):
    """Complete design-rules profile."""

    name: str
    content_limits: ContentLimits
    hierarchy: HierarchyRules
    overflow_policy: OverflowPolicy
    deck_structure: DeckStructureRules
    layout_hints: LayoutHints = Field(default_factory=LayoutHints)
    normalize_font_sizes: bool = True
    type_ladders: dict[str, list[float]] = Field(
        default_factory=lambda: {role: list(sizes) for role, sizes in DEFAULT_TYPE_LADDERS.items()}
    )
    conditional_formatting: ConditionalFormatting = Field(default_factory=ConditionalFormatting)

    @field_validator("type_ladders")
    @classmethod
    def validate_type_ladders(cls, value: dict[str, list[float]]) -> dict[str, list[float]]:
        normalized: dict[str, list[float]] = {}
        for role, sizes in value.items():
            if not sizes:
                raise ValueError(f"type ladder for role '{role}' cannot be empty")
            ladder = [float(size) for size in sizes]
            if any(size <= 0 for size in ladder):
                raise ValueError(f"type ladder for role '{role}' must contain positive sizes")
            normalized[role] = ladder
        return normalized


def _design_rules_dir() -> resources.abc.Traversable:
    return resources.files("agent_slides.config.design_rules")


def load_design_rules(name: str) -> DesignRules:
    """Load design rules by name from config directory."""

    resource = _design_rules_dir().joinpath(f"{name}.yaml")
    if not resource.is_file():
        raise AgentSlidesError(
            FILE_NOT_FOUND,
            f"Design rules profile '{name}' was not found.",
        )

    try:
        with resource.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        return DesignRules.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise AgentSlidesError(
            SCHEMA_ERROR,
            f"Failed to load design rules profile '{name}'.",
        ) from exc


def list_design_rules() -> list[str]:
    """Return sorted list of available design-rule profile names."""

    return sorted(
        Path(resource.name).stem
        for resource in _design_rules_dir().iterdir()
        if resource.is_file() and resource.name.endswith(".yaml")
    )
