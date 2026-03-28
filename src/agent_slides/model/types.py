"""Core Pydantic types for the scene graph and theme system."""

from __future__ import annotations

import warnings
from math import isclose
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from agent_slides.errors import (
    AgentSlidesError,
    CHART_DATA_ERROR,
    INVALID_CHART_TYPE,
    INVALID_SLIDE,
)

STANDARD_SLIDE_WIDTH_PT = 720.0
STANDARD_SLIDE_HEIGHT_PT = 540.0
EMU_PER_POINT = 12_700
MAX_IMAGE_SIZE_WARNING_BYTES = 5 * 1024 * 1024
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".svg"})
CHART_TYPE_VALUES = ("bar", "column", "line", "pie", "scatter", "area", "doughnut")

ChartType = Literal["bar", "column", "line", "pie", "scatter", "area", "doughnut"]
NodeType = Literal["text", "image", "chart"]
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
    font_size_pt: float
    font_family: str
    color: str
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


class ChartSeries(AgentSlidesModel):
    name: str
    values: list[float]

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: list[float]) -> list[float]:
        if not value:
            raise PydanticCustomError(CHART_DATA_ERROR, "chart series values cannot be empty")
        return value


class ScatterPoint(AgentSlidesModel):
    x: float
    y: float


class ScatterSeries(AgentSlidesModel):
    name: str
    points: list[ScatterPoint]

    @field_validator("points")
    @classmethod
    def validate_points(cls, value: list[ScatterPoint]) -> list[ScatterPoint]:
        if not value:
            raise PydanticCustomError(CHART_DATA_ERROR, "scatter series points cannot be empty")
        return value


class ChartStyle(AgentSlidesModel):
    has_legend: bool = True
    has_data_labels: bool = False
    series_colors: list[str] | None = None

    @field_validator("series_colors")
    @classmethod
    def validate_series_colors(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        for value in values:
            normalized = value.lstrip("#")
            if len(normalized) != 6 or any(char not in "0123456789abcdefABCDEF" for char in normalized):
                raise ValueError("series_colors entries must use #RRGGBB or RRGGBB format")
        return values


class ChartSpec(AgentSlidesModel):
    chart_type: ChartType
    title: str | None = None
    categories: list[str] | None = None
    series: list[ChartSeries] | None = None
    scatter_series: list[ScatterSeries] | None = None
    style: ChartStyle = Field(default_factory=ChartStyle)

    @field_validator("chart_type", mode="before")
    @classmethod
    def validate_chart_type(cls, value: object) -> object:
        if not isinstance(value, str) or value not in CHART_TYPE_VALUES:
            raise PydanticCustomError(INVALID_CHART_TYPE, "unknown chart type: {chart_type}", {"chart_type": value})
        return value

    @model_validator(mode="after")
    def validate_chart_data(self) -> ChartSpec:
        if self.chart_type == "scatter":
            if self.categories or self.series:
                raise PydanticCustomError(CHART_DATA_ERROR, "scatter charts only support scatter_series")
            if not self.scatter_series:
                raise PydanticCustomError(CHART_DATA_ERROR, "scatter charts require scatter_series")
            if len(self.scatter_series) > 10:
                warnings.warn(
                    "Chart spec contains more than 10 series and may be difficult to read.",
                    UserWarning,
                    stacklevel=2,
                )
            return self

        if self.scatter_series:
            raise PydanticCustomError(CHART_DATA_ERROR, "category charts cannot define scatter_series")
        if not self.categories:
            raise PydanticCustomError(CHART_DATA_ERROR, "category charts require categories")
        if not self.series:
            raise PydanticCustomError(CHART_DATA_ERROR, "category charts require series")

        category_count = len(self.categories)
        for series in self.series:
            if len(series.values) != category_count:
                raise PydanticCustomError(
                    CHART_DATA_ERROR,
                    "series '{series_name}' has {value_count} values for {category_count} categories",
                    {
                        "series_name": series.name,
                        "value_count": len(series.values),
                        "category_count": category_count,
                    },
                )

        if self.chart_type == "pie":
            if len(self.series) > 1:
                raise PydanticCustomError(CHART_DATA_ERROR, "pie charts support exactly one series")
            if any(value < 0 for value in self.series[0].values):
                warnings.warn(
                    "Pie charts contain negative values; PowerPoint may render them unexpectedly.",
                    UserWarning,
                    stacklevel=2,
                )

        if len(self.series) > 10:
            warnings.warn(
                "Chart spec contains more than 10 series and may be difficult to read.",
                UserWarning,
                stacklevel=2,
            )
        return self


class Node(AgentSlidesModel):
    node_id: str
    slot_binding: str | None = None
    type: NodeType
    content: NodeContent | str = Field(default_factory=NodeContent)
    image_path: str | None = None
    chart_spec: ChartSpec | None = None
    style_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def validate_node_payload(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        node_type = data.get("type", "text")
        content = data.get("content")

        if node_type == "text":
            data["content"] = NodeContent.model_validate(content)
        elif node_type == "chart":
            if data.get("chart_spec") is None and content not in (None, "", {"blocks": []}):
                raw_chart_spec = content
                if isinstance(raw_chart_spec, str):
                    raw_chart_spec = ChartSpec.model_validate_json(raw_chart_spec)
                else:
                    raw_chart_spec = ChartSpec.model_validate(raw_chart_spec)
                data["chart_spec"] = (
                    raw_chart_spec.model_dump(mode="json")
                    if isinstance(raw_chart_spec, ChartSpec)
                    else raw_chart_spec
                )
                data["content"] = NodeContent().model_dump(mode="json")
            else:
                data["content"] = NodeContent.model_validate(content)
            if data.get("chart_spec") is not None:
                data["chart_spec"] = ChartSpec.model_validate(data["chart_spec"]).model_dump(mode="json")
        elif node_type == "image" and (content is None or content == "") and data.get("image_path") is not None:
            data["content"] = data["image_path"]

        return data

    @model_validator(mode="after")
    def validate_node_type_specific_fields(self) -> Node:
        if self.type == "text":
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if self.image_path is not None:
                raise ValueError("text nodes cannot define image_path")
            if self.chart_spec is not None:
                raise ValueError("text nodes cannot define chart_spec")
            return self

        if self.type == "image":
            if self.chart_spec is not None:
                raise ValueError("image nodes cannot define chart_spec")
            if not self.image_path:
                if self.style_overrides.get("placeholder"):
                    self.content = ""
                    return self
                raise ValueError("image nodes require image_path")
            if not isinstance(self.content, str):
                raise ValueError("image nodes must serialize content as a file path string")

            self.image_path = _validate_and_resolve_image_path(self.image_path)
            return self

        if self.image_path is not None:
            raise ValueError("chart nodes cannot define image_path")
        if self.chart_spec is None:
            raise ValueError("chart nodes require chart_spec")
        if not isinstance(self.content, NodeContent):
            self.content = NodeContent.model_validate(self.content)
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
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
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


def _validate_and_resolve_image_path(value: str) -> str:
    path = Path(value).expanduser()
    resolved_path = path.resolve(strict=False)
    suffix = resolved_path.suffix.lower()

    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_IMAGE_EXTENSIONS))
        raise ValueError(f"image_path must use a supported image format: {supported}")
    if not resolved_path.exists():
        raise ValueError(f"image_path does not exist: {resolved_path}")
    if not resolved_path.is_file():
        raise ValueError(f"image_path must point to a file: {resolved_path}")

    try:
        with resolved_path.open("rb"):
            pass
    except OSError as exc:
        raise ValueError(f"image_path is not readable: {resolved_path}") from exc

    size_bytes = resolved_path.stat().st_size
    if size_bytes > MAX_IMAGE_SIZE_WARNING_BYTES:
        warnings.warn(
            f"Image file '{resolved_path}' is larger than 5MB and may bloat output decks.",
            UserWarning,
            stacklevel=3,
        )

    return str(resolved_path)


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
