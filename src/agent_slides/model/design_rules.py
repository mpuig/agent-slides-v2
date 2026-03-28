"""Design-rules models and packaged profile loading."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from agent_slides.errors import AgentSlidesError, FILE_NOT_FOUND, SCHEMA_ERROR


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


class BlockSpacingRules(BaseModel):
    """Spacing between consecutive structured text block types."""

    heading_to_paragraph: float = 12.0
    heading_to_bullet: float = 10.0
    paragraph_to_paragraph: float = 6.0
    paragraph_to_bullet: float = 8.0
    bullet_to_bullet: float = 4.0
    bullet_to_paragraph: float = 8.0
    default: float = 6.0

    def between(self, previous: str, current: str) -> float:
        return {
            ("heading", "paragraph"): self.heading_to_paragraph,
            ("heading", "bullet"): self.heading_to_bullet,
            ("paragraph", "paragraph"): self.paragraph_to_paragraph,
            ("paragraph", "bullet"): self.paragraph_to_bullet,
            ("bullet", "bullet"): self.bullet_to_bullet,
            ("bullet", "paragraph"): self.bullet_to_paragraph,
        }.get((previous, current), self.default)


class DesignRules(BaseModel):
    """Complete design-rules profile."""

    name: str
    content_limits: ContentLimits
    hierarchy: HierarchyRules
    overflow_policy: OverflowPolicy
    deck_structure: DeckStructureRules
    layout_hints: LayoutHints = Field(default_factory=LayoutHints)
    block_spacing: BlockSpacingRules = Field(default_factory=BlockSpacingRules)


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
