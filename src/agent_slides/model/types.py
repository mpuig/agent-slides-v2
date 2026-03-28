"""Core Pydantic types for the scene graph and theme system."""

from __future__ import annotations

from math import isclose
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_slides.errors import AgentSlidesError, INVALID_SLIDE

STANDARD_SLIDE_WIDTH_PT = 720.0
STANDARD_SLIDE_HEIGHT_PT = 540.0
EMU_PER_POINT = 12_700

NodeType = Literal["text", "image"]
ImageFit = Literal["contain", "cover", "stretch"]
SlotRole = Literal["heading", "body", "quote", "attribution", "image"]


class AgentSlidesModel(BaseModel):
    """Common Pydantic defaults for scene-graph models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_by_alias=True,
        validate_by_name=True,
    )


class ComputedNode(AgentSlidesModel):
    x: float
    y: float
    width: float
    height: float
    font_size_pt: float = 0.0
    font_family: str = ""
    color: str = "#000000"
    bg_color: str | None = None
    bg_transparency: float = 0.0
    font_bold: bool = False
    text_overflow: bool = False
    revision: int
    content_type: NodeType = "text"
    image_fit: ImageFit = "contain"


class TextBlock(AgentSlidesModel):
    type: Literal["paragraph", "bullet", "heading"]
    text: str
    level: int = 0

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: int) -> int:
        if value < 0:
            raise ValueError("level must be greater than or equal to 0")
        return value


class NodeContent(AgentSlidesModel):
    blocks: list[TextBlock] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_content(cls, value: object) -> object:
        if value is None:
            return {"blocks": []}
        if isinstance(value, str):
            return cls.from_text(value).model_dump(mode="json")
        if isinstance(value, list):
            return {"blocks": value}
        return value

    @classmethod
    def from_text(cls, text: str, *, block_type: Literal["paragraph", "bullet", "heading"] = "paragraph") -> NodeContent:
        if text == "":
            return cls()
        return cls(blocks=[TextBlock(type=block_type, text=text)])

    def to_plain_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def word_count(self) -> int:
        return sum(len(block.text.split()) for block in self.blocks)

    def bullet_count(self) -> int:
        return sum(1 for block in self.blocks if block.type == "bullet")

    def is_empty(self) -> bool:
        return not self.blocks or all(block.text == "" for block in self.blocks)


class Node(AgentSlidesModel):
    node_id: str
    slot_binding: str | None = None
    type: NodeType
    content: NodeContent = Field(default_factory=NodeContent)
    image_path: str | None = None
    image_fit: ImageFit = "contain"
    style_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_content_by_type(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        data["content"] = NodeContent.model_validate(data.get("content"))
        return data

    @model_validator(mode="after")
    def validate_node_payload(self) -> Node:
        if self.type == "text":
            if self.image_path is not None:
                raise ValueError("text nodes cannot define image_path")
            return self

        if self.image_path is None or not self.image_path.strip():
            if self.style_overrides.get("placeholder"):
                return self
            raise ValueError("image nodes require image_path")
        if not self.content.is_empty():
            raise ValueError("image nodes cannot define text content")
        self.image_path = self.image_path.strip()
        return self


class Slide(AgentSlidesModel):
    slide_id: str
    layout: str
    nodes: list[Node] = Field(default_factory=list)
    computed: dict[str, ComputedNode] = Field(default_factory=dict)


class ThemeColors(AgentSlidesModel):
    primary: str
    secondary: str
    accent: str
    background: str
    text: str
    heading_text: str | None = None
    subtle_text: str | None = None

    @model_validator(mode="after")
    def apply_role_defaults(self) -> ThemeColors:
        if self.heading_text is None:
            self.heading_text = self.primary
        if self.subtle_text is None:
            self.subtle_text = self.text
        return self


class ThemeFonts(AgentSlidesModel):
    heading: str
    body: str


class ThemeSpacing(AgentSlidesModel):
    base_unit: float
    margin: float
    gutter: float


class Theme(AgentSlidesModel):
    name: str
    colors: ThemeColors
    fonts: ThemeFonts
    spacing: ThemeSpacing


class SlotDef(AgentSlidesModel):
    grid_row: int | list[int]
    grid_col: int | list[int]
    role: SlotRole
    full_bleed: bool = False
    bg_color: str | None = None
    bg_transparency: float = 0.0

    @field_validator("bg_transparency")
    @classmethod
    def validate_bg_transparency(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("bg_transparency must be between 0.0 and 1.0")
        return value


class GridDef(AgentSlidesModel):
    columns: int
    rows: int
    row_heights: list[float]
    col_widths: list[float]
    margin: float
    gutter: float

    @model_validator(mode="after")
    def validate_proportions(self) -> GridDef:
        if len(self.row_heights) != self.rows:
            raise ValueError("row_heights length must match rows")
        if len(self.col_widths) != self.columns:
            raise ValueError("col_widths length must match columns")
        if not isclose(sum(self.row_heights), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("row_heights must sum to 1.0")
        if not isclose(sum(self.col_widths), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("col_widths must sum to 1.0")
        return self


class TextFitting(AgentSlidesModel):
    default_size: float
    min_size: float = 10.0


class LayoutDef(AgentSlidesModel):
    name: str
    slots: dict[str, SlotDef]
    grid: GridDef
    text_fitting: dict[str, TextFitting]


class Counters(AgentSlidesModel):
    slides: int = 0
    nodes: int = 0


class Deck(AgentSlidesModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    version: int = 2
    deck_id: str
    revision: int = 0
    theme: str = "default"
    design_rules: str = "default"
    template_manifest: str | None = None
    slides: list[Slide] = Field(default_factory=list)
    counters: Counters = Field(default_factory=Counters, alias="_counters")

    def next_slide_id(self) -> str:
        self.counters.slides += 1
        return f"s-{self.counters.slides}"

    def next_node_id(self) -> str:
        self.counters.nodes += 1
        return f"n-{self.counters.nodes}"

    def bump_revision(self) -> None:
        self.revision += 1

    def get_slide(self, ref: str | int) -> Slide:
        if isinstance(ref, int):
            if 0 <= ref < len(self.slides):
                return self.slides[ref]
            raise AgentSlidesError(INVALID_SLIDE, f"Slide index {ref} is out of range")

        for slide in self.slides:
            if slide.slide_id == ref:
                return slide

        raise AgentSlidesError(INVALID_SLIDE, f"Slide {ref!r} does not exist")


class ComputedSlide(AgentSlidesModel):
    slide_id: str
    computed: dict[str, ComputedNode] = Field(default_factory=dict)


class ComputedDeck(AgentSlidesModel):
    version: int = 2
    deck_id: str
    revision: int = 0
    slides: list[ComputedSlide] = Field(default_factory=list)

    @classmethod
    def from_deck(cls, deck: Deck) -> ComputedDeck:
        return cls(
            deck_id=deck.deck_id,
            revision=deck.revision,
            slides=[
                ComputedSlide(
                    slide_id=slide.slide_id,
                    computed=slide.computed,
                )
                for slide in deck.slides
            ],
        )

    def apply_to_deck(self, deck: Deck) -> None:
        for slide in deck.slides:
            slide.computed = {}

        if self.deck_id != deck.deck_id or self.revision != deck.revision:
            return

        slides_by_id = {slide.slide_id: slide for slide in deck.slides}
        for computed_slide in self.slides:
            slide = slides_by_id.get(computed_slide.slide_id)
            if slide is None:
                continue
            slide.computed = dict(computed_slide.computed)
