"""Core scene-graph and theme models."""

from __future__ import annotations

from math import isclose
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_slides.errors import AgentSlidesError, INVALID_SLIDE

STANDARD_SLIDE_WIDTH_PT = 720.0
STANDARD_SLIDE_HEIGHT_PT = 540.0
EMU_PER_POINT = 12_700


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
    font_size_pt: float
    font_family: str
    color: str
    bg_color: str | None = None
    font_bold: bool = False
    revision: int


class Node(AgentSlidesModel):
    node_id: str
    slot_binding: str | None = None
    type: Literal["text"]
    content: str = ""
    style_overrides: dict[str, Any] = Field(default_factory=dict)


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
    grid_row: int
    grid_col: int | list[int]
    role: str


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

    version: int = 1
    deck_id: str
    revision: int = 0
    theme: str = "default"
    design_rules: str = "default"
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
