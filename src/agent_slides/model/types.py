"""Core Pydantic types for the scene graph and theme system."""

from __future__ import annotations

import warnings
from math import isclose
import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticCustomError

from agent_slides.errors import (
    AgentSlidesError,
    CHART_DATA_ERROR,
    INVALID_CHART_TYPE,
    INVALID_ICON,
    INVALID_SLIDE,
)
from agent_slides.icons import has_icon, normalize_hex_color

STANDARD_SLIDE_WIDTH_PT = 720.0
STANDARD_SLIDE_HEIGHT_PT = 540.0
EMU_PER_POINT = 12_700
CHART_TYPE_VALUES = ("bar", "column", "line", "pie", "scatter", "area", "doughnut")
SHAPE_TYPE_VALUES = (
    "rectangle",
    "rounded_rectangle",
    "line",
    "oval",
    "arrow",
    "chevron",
)
SHAPE_DASH_VALUES = ("dash", "dot", "dashDot")
PATTERN_TYPE_VALUES = (
    "kpi-row",
    "card-grid",
    "process-flow",
    "chevron-flow",
    "comparison-cards",
    "icon-row",
)

ChartType = Literal["bar", "column", "line", "pie", "scatter", "area", "doughnut"]
ShapeType = Literal[
    "rectangle", "rounded_rectangle", "line", "oval", "arrow", "chevron"
]
ShapeDash = Literal["dash", "dot", "dashDot"]
PatternType = Literal[
    "kpi-row",
    "card-grid",
    "process-flow",
    "chevron-flow",
    "comparison-cards",
    "icon-row",
]
PatternElementKind = Literal["shape", "text"]
TableAlign = Literal["left", "center", "right"]
NodeType = Literal["text", "image", "chart", "table", "icon", "shape", "pattern"]
ImageFit = Literal["contain", "cover", "stretch"]
SlotRole = Literal["heading", "body", "quote", "attribution", "image"]
ConstraintHeightMode = Literal["fixed", "fit_content", "fill_remaining"]
ConstraintWidthMode = Literal["fixed", "equal_share"]
SlotVerticalAlign = Literal["top", "middle", "bottom"]
_HEX_COLOR_DIGITS = frozenset("0123456789abcdefABCDEF")


TABLE_ALIGN_VALUES = ("left", "center", "right")
_HEX_COLOR_PATTERN = re.compile(r"^#?[0-9A-Fa-f]{6}$")
_NUMERIC_TABLE_VALUE_PATTERN = re.compile(
    r"^\s*[\(\-+]?\s*(?:[$€£¥]\s*)?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\d*\.\d+)\s*(?:[KMBT]|bn|mm)?\s*%?\s*\)?\s*$",
    re.IGNORECASE,
)


def _normalize_hex_color(value: str, *, field_name: str = "color") -> str:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6 or any(
        char not in _HEX_COLOR_DIGITS for char in normalized
    ):
        raise ValueError(f"{field_name} must use #RRGGBB or RRGGBB format")
    return f"#{normalized.upper()}"


def _normalize_run_color(value: str) -> str:
    return _normalize_hex_color(value, field_name="color")


def _looks_numeric_table_value(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and bool(_NUMERIC_TABLE_VALUE_PATTERN.match(stripped))


class AgentSlidesModel(BaseModel):
    """Common Pydantic defaults for scene-graph models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_by_alias=True,
        validate_by_name=True,
    )


class BlockPosition(AgentSlidesModel):
    block_index: int
    x: float
    y: float
    width: float
    height: float
    font_size_pt: float


class ComputedPatternElement(AgentSlidesModel):
    kind: PatternElementKind
    x: float
    y: float
    width: float
    height: float
    z_index: int = 0
    shape_type: ShapeType | None = None
    fill_color: str | None = None
    line_color: str | None = None
    line_width: float = 0.0
    corner_radius: float = 0.0
    shadow: bool = False
    dash: ShapeDash | None = None
    opacity: float = 1.0
    text: str | None = None
    font_size_pt: float = 0.0
    font_family: str = ""
    color: str = "#000000"
    font_bold: bool = False
    text_align: TableAlign = "left"
    vertical_align: SlotVerticalAlign = "top"

    @field_validator("shape_type", mode="before")
    @classmethod
    def validate_shape_type(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or value not in SHAPE_TYPE_VALUES:
            raise ValueError(
                f"shape_type must be one of: {', '.join(SHAPE_TYPE_VALUES)}"
            )
        return value

    @field_validator("fill_color", "line_color", "color")
    @classmethod
    def validate_color(cls, value: str | None, info) -> str | None:
        if value is None:
            return value
        return _normalize_hex_color(value, field_name=info.field_name)

    @field_validator("line_width", "corner_radius", "font_size_pt")
    @classmethod
    def validate_non_negative_dimension(cls, value: float, info) -> float:
        if value < 0:
            raise ValueError(f"{info.field_name} must be greater than or equal to 0")
        return float(value)

    @field_validator("dash", mode="before")
    @classmethod
    def validate_dash(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or value not in SHAPE_DASH_VALUES:
            raise ValueError(f"dash must be one of: {', '.join(SHAPE_DASH_VALUES)}")
        return value

    @field_validator("opacity")
    @classmethod
    def validate_opacity(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("opacity must be between 0.0 and 1.0")
        return float(value)

    @model_validator(mode="after")
    def validate_kind_specific_fields(self) -> ComputedPatternElement:
        if self.kind == "shape":
            if self.shape_type is None:
                raise ValueError("shape elements require shape_type")
            if self.text is not None:
                raise ValueError("shape elements cannot define text")
            return self
        if self.text is None:
            raise ValueError("text elements require text")
        if self.font_size_pt <= 0:
            raise ValueError("text elements require font_size_pt greater than 0")
        return self


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
    layout_used: str | None = None
    layout_fallback_reason: str | None = None
    layout_overflow_reason: str | None = None
    icon_svg_path: str | None = None
    block_positions: list[BlockPosition] = Field(default_factory=list)
    pattern_elements: list[ComputedPatternElement] = Field(default_factory=list)


class TextRun(AgentSlidesModel):
    text: str
    bold: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    italic: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    color: str | None = Field(default=None, exclude_if=lambda value: value is None)
    font_size: float | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    underline: bool = Field(default=False, exclude_if=lambda value: value is False)
    strikethrough: bool = Field(default=False, exclude_if=lambda value: value is False)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_run_color(value)

    @field_validator("font_size")
    @classmethod
    def validate_font_size(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("font_size must be greater than 0")
        return float(value)


class TextBlock(AgentSlidesModel):
    type: Literal["paragraph", "bullet", "heading"]
    text: str = ""
    level: int = 0
    runs: list[TextRun] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    icon: str | None = None

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: int) -> int:
        if value < 0:
            raise ValueError("level must be greater than or equal to 0")
        return value

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("icon must be a non-empty string")
        if not has_icon(normalized):
            raise AgentSlidesError(INVALID_ICON, f"Unknown icon {value!r}")
        return normalized

    @model_validator(mode="after")
    def normalize_text_from_runs(self) -> TextBlock:
        if self.runs is not None:
            self.text = "".join(run.text for run in self.runs)
        return self

    def resolved_runs(self) -> list[TextRun]:
        if self.runs is not None:
            return list(self.runs)
        return [TextRun(text=self.text)]

    @model_serializer(mode="plain")
    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "text": self.text,
            "level": self.level,
        }
        if self.runs is not None:
            payload["runs"] = [run.model_dump(mode="json") for run in self.runs]
        if self.icon is not None:
            payload["icon"] = self.icon
        return payload


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
    def from_text(
        cls,
        text: str,
        *,
        block_type: Literal["paragraph", "bullet", "heading"] = "paragraph",
    ) -> NodeContent:
        if text == "":
            return cls()
        if block_type != "paragraph":
            return cls(blocks=[TextBlock(type=block_type, text=text)])
        return cls(blocks=parse_text_blocks(text))

    def to_plain_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def word_count(self) -> int:
        return sum(len(block.text.split()) for block in self.blocks)

    def bullet_count(self) -> int:
        return sum(1 for block in self.blocks if block.type == "bullet")

    def is_empty(self) -> bool:
        return not self.blocks or all(block.text == "" for block in self.blocks)


def parse_inline_markdown_runs(text: str) -> list[TextRun] | None:
    """Parse a minimal inline markdown dialect supporting **bold** and *italic* spans."""

    if text == "":
        return None

    runs: list[TextRun] = []
    buffer: list[str] = []
    bold = False
    italic = False
    saw_markup = False
    index = 0

    def flush() -> None:
        if not buffer:
            return
        payload: dict[str, object] = {"text": "".join(buffer)}
        if bold:
            payload["bold"] = True
        if italic:
            payload["italic"] = True
        runs.append(TextRun.model_validate(payload))
        buffer.clear()

    while index < len(text):
        if text.startswith("**", index) and (bold or text.find("**", index + 2) != -1):
            flush()
            bold = not bold
            saw_markup = True
            index += 2
            continue
        if text[index] == "*" and (italic or text.find("*", index + 1) != -1):
            flush()
            italic = not italic
            saw_markup = True
            index += 1
            continue
        buffer.append(text[index])
        index += 1

    flush()
    if not saw_markup:
        return None
    return _merge_adjacent_runs(runs) or [TextRun(text="")]


_INLINE_COLOR_PATTERN = re.compile(r"^\{([A-Za-z0-9#_-]+)\}")


def apply_inline_color_suffixes(
    runs: list[TextRun],
    *,
    color_aliases: dict[str, str] | None = None,
) -> list[TextRun]:
    """Apply `**text**{color}` suffixes to the preceding run."""

    if not runs:
        return [TextRun(text="")]

    aliases = {key.casefold(): value for key, value in (color_aliases or {}).items()}
    resolved: list[TextRun] = []

    def resolve_color(token: str) -> str | None:
        normalized = token.strip()
        if not normalized:
            return None
        alias = aliases.get(normalized.casefold())
        if alias is not None:
            return _normalize_run_color(alias)
        try:
            return _normalize_run_color(normalized)
        except ValueError:
            return None

    for run in runs:
        current = run
        while resolved and current.text:
            match = _INLINE_COLOR_PATTERN.match(current.text)
            if match is None:
                break
            color = resolve_color(match.group(1))
            if color is None:
                break
            previous = resolved[-1]
            resolved[-1] = previous.model_copy(update={"color": color})
            current = current.model_copy(update={"text": current.text[match.end() :]})
        if current.text:
            resolved.append(current)

    return _merge_adjacent_runs(resolved) or [TextRun(text="")]


def split_text_runs_by_line(block: TextBlock) -> list[list[TextRun]]:
    """Split a block into line-oriented runs while preserving inline formatting."""

    line_runs: list[list[TextRun]] = [[]]
    for run in block.resolved_runs():
        parts = run.text.splitlines(keepends=True) or [""]
        for part in parts:
            has_line_break = part.endswith("\n") or part.endswith("\r")
            text = part.rstrip("\r\n")
            if text or not line_runs[-1]:
                line_runs[-1].append(run.model_copy(update={"text": text}))
            if has_line_break:
                line_runs.append([])
    return line_runs or [[TextRun(text="")]]


def parse_text_blocks(text: str) -> list[TextBlock]:
    if "\n" not in text:
        return [TextBlock(type="paragraph", text=text)]

    lines = text.splitlines()
    if not any(_is_bullet_line(line) for line in lines):
        return [TextBlock(type="paragraph", text=text)]

    blocks: list[TextBlock] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_bullet_line(stripped):
            blocks.append(TextBlock(type="bullet", text=stripped[2:]))
            continue
        blocks.append(TextBlock(type="paragraph", text=stripped))
    return blocks


def _is_bullet_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("- ") or stripped.startswith("* ")


def _merge_adjacent_runs(runs: list[TextRun]) -> list[TextRun]:
    merged: list[TextRun] = []
    for run in runs:
        if run.text == "":
            continue
        if not merged:
            merged.append(run)
            continue
        previous = merged[-1]
        same_style = (
            previous.bold == run.bold
            and previous.italic == run.italic
            and previous.color == run.color
            and previous.font_size == run.font_size
            and previous.underline == run.underline
            and previous.strikethrough == run.strikethrough
        )
        if same_style:
            merged[-1] = previous.model_copy(update={"text": previous.text + run.text})
            continue
        merged.append(run)
    return merged


class ChartSeries(AgentSlidesModel):
    name: str
    values: list[float]

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: list[float]) -> list[float]:
        if not value:
            raise PydanticCustomError(
                CHART_DATA_ERROR, "chart series values cannot be empty"
            )
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
            raise PydanticCustomError(
                CHART_DATA_ERROR, "scatter series points cannot be empty"
            )
        return value


class ChartStyle(AgentSlidesModel):
    has_legend: bool = True
    has_data_labels: bool = False
    series_colors: list[str] | None = None
    color_by_value: bool = False
    highlight_index: int | None = None
    highlight_color: str | None = None
    muted_color: str | None = None

    @field_validator("series_colors")
    @classmethod
    def validate_series_colors(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        for value in values:
            try:
                _normalize_run_color(value)
            except ValueError as exc:
                raise ValueError(
                    "series_colors entries must use #RRGGBB or RRGGBB format"
                ) from exc
        return values

    @field_validator("highlight_color", "muted_color")
    @classmethod
    def validate_optional_colors(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_run_color(value)

    @field_validator("highlight_index")
    @classmethod
    def validate_highlight_index(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 0:
            raise ValueError("highlight_index must be greater than or equal to 0")
        return value


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
            raise PydanticCustomError(
                INVALID_CHART_TYPE,
                "unknown chart type: {chart_type}",
                {"chart_type": value},
            )
        return value

    @model_validator(mode="after")
    def validate_chart_data(self) -> ChartSpec:
        if self.chart_type == "scatter":
            if self.categories or self.series:
                raise PydanticCustomError(
                    CHART_DATA_ERROR, "scatter charts only support scatter_series"
                )
            if not self.scatter_series:
                raise PydanticCustomError(
                    CHART_DATA_ERROR, "scatter charts require scatter_series"
                )
            if len(self.scatter_series) > 10:
                warnings.warn(
                    "Chart spec contains more than 10 series and may be difficult to read.",
                    UserWarning,
                    stacklevel=2,
                )
            return self

        if self.scatter_series:
            raise PydanticCustomError(
                CHART_DATA_ERROR, "category charts cannot define scatter_series"
            )
        if not self.categories:
            raise PydanticCustomError(
                CHART_DATA_ERROR, "category charts require categories"
            )
        if not self.series:
            raise PydanticCustomError(
                CHART_DATA_ERROR, "category charts require series"
            )

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
                raise PydanticCustomError(
                    CHART_DATA_ERROR, "pie charts support exactly one series"
                )
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


class ShapeSpec(AgentSlidesModel):
    shape_type: ShapeType
    fill_color: str | None = None
    line_color: str | None = None
    line_width: float = 1.0
    corner_radius: float = 0.0
    shadow: bool = False
    dash: ShapeDash | None = None
    opacity: float = 1.0

    @field_validator("shape_type", mode="before")
    @classmethod
    def validate_shape_type(cls, value: object) -> object:
        if not isinstance(value, str) or value not in SHAPE_TYPE_VALUES:
            raise ValueError(
                f"shape_type must be one of: {', '.join(SHAPE_TYPE_VALUES)}"
            )
        return value

    @field_validator("fill_color", "line_color")
    @classmethod
    def validate_color(cls, value: str | None, info) -> str | None:
        if value is None:
            return value
        return _normalize_hex_color(value, field_name=info.field_name)

    @field_validator("line_width", "corner_radius")
    @classmethod
    def validate_non_negative_dimension(cls, value: float, info) -> float:
        if value < 0:
            raise ValueError(f"{info.field_name} must be greater than or equal to 0")
        return value

    @field_validator("dash", mode="before")
    @classmethod
    def validate_dash(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or value not in SHAPE_DASH_VALUES:
            raise ValueError(f"dash must be one of: {', '.join(SHAPE_DASH_VALUES)}")
        return value

    @field_validator("opacity")
    @classmethod
    def validate_opacity(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("opacity must be between 0.0 and 1.0")
        return value


class TableSpec(AgentSlidesModel):
    headers: list[str]
    rows: list[list[str]]
    col_widths: list[float] | None = None
    col_align: list[TableAlign] | None = None
    header_color: str | None = None
    stripe: bool = True
    font_size: float = 11.0
    header_font_size: float = 12.0

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("headers must contain at least one column")
        normalized = [header.strip() for header in value]
        if any(not header for header in normalized):
            raise ValueError("headers cannot contain empty values")
        return normalized

    @field_validator("col_widths")
    @classmethod
    def validate_col_widths(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("col_widths must contain at least one value when provided")
        if any(width <= 0 for width in value):
            raise ValueError("col_widths entries must be greater than 0")
        return [float(width) for width in value]

    @field_validator("col_align")
    @classmethod
    def validate_col_align(
        cls, value: list[TableAlign] | None
    ) -> list[TableAlign] | None:
        if value is None:
            return value
        return [alignment.strip().lower() for alignment in value]

    @field_validator("header_color")
    @classmethod
    def validate_header_color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_hex_color(value, field_name="header_color")

    @field_validator("font_size", "header_font_size")
    @classmethod
    def validate_font_sizes(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("font sizes must be greater than 0")
        return float(value)

    @model_validator(mode="after")
    def validate_table_shape(self) -> TableSpec:
        column_count = len(self.headers)
        for row_index, row in enumerate(self.rows):
            if len(row) != column_count:
                raise ValueError(
                    f"rows[{row_index}] has {len(row)} values for {column_count} headers"
                )
        if self.col_widths is not None and len(self.col_widths) != column_count:
            raise ValueError("col_widths length must match headers")
        if self.col_align is not None and len(self.col_align) != column_count:
            raise ValueError("col_align length must match headers")
        return self

    def infer_numeric_columns(self) -> list[bool]:
        inferred: list[bool] = []
        for column_index in range(len(self.headers)):
            values = [
                row[column_index] for row in self.rows if row[column_index].strip()
            ]
            inferred.append(
                bool(values)
                and all(_looks_numeric_table_value(value) for value in values)
            )
        return inferred

    def resolved_col_align(self) -> list[TableAlign]:
        if self.col_align is not None:
            return list(self.col_align)
        numeric_columns = self.infer_numeric_columns()
        return ["right" if is_numeric else "left" for is_numeric in numeric_columns]

    def resolved_col_widths(self) -> list[float]:
        if self.col_widths is not None:
            return list(self.col_widths)

        weights: list[float] = []
        numeric_columns = self.infer_numeric_columns()
        for column_index, header in enumerate(self.headers):
            values = [header, *(row[column_index] for row in self.rows)]
            max_length = max(
                len(value.strip()) for value in values if value is not None
            )
            weight = max(1.0, float(max_length))
            if not numeric_columns[column_index]:
                weight += 2.0
            weights.append(weight)
        return weights


class PatternSpec(AgentSlidesModel):
    pattern_type: PatternType
    data: dict[str, Any] | list[Any]
    columns: int | None = None

    @field_validator("pattern_type", mode="before")
    @classmethod
    def validate_pattern_type(cls, value: object) -> object:
        if not isinstance(value, str) or value not in PATTERN_TYPE_VALUES:
            raise ValueError(
                f"pattern_type must be one of: {', '.join(PATTERN_TYPE_VALUES)}"
            )
        return value

    @field_validator("data")
    @classmethod
    def validate_data(
        cls, value: dict[str, Any] | list[Any]
    ) -> dict[str, Any] | list[Any]:
        if not isinstance(value, dict | list):
            raise ValueError("data must be a JSON object or array")
        return value

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("columns must be greater than 0")
        return value


class Node(AgentSlidesModel):
    node_id: str
    slot_binding: str | None = None
    type: NodeType
    content: NodeContent = Field(default_factory=NodeContent)
    image_path: str | None = None
    image_fit: ImageFit = "contain"
    chart_spec: ChartSpec | None = None
    shape_spec: ShapeSpec | None = None
    table_spec: TableSpec | None = None
    pattern_spec: PatternSpec | None = None
    icon_name: str | None = None
    x: float | None = None
    y: float | None = None
    size: float | None = None
    color: str | None = None
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
            if data.get("chart_spec") is None and content not in (
                None,
                "",
                {"blocks": []},
            ):
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
                data["chart_spec"] = ChartSpec.model_validate(
                    data["chart_spec"]
                ).model_dump(mode="json")
        elif node_type == "shape":
            data["content"] = NodeContent.model_validate(content)
            if data.get("shape_spec") is not None:
                data["shape_spec"] = ShapeSpec.model_validate(
                    data["shape_spec"]
                ).model_dump(mode="json")
        elif node_type == "pattern":
            data["content"] = NodeContent.model_validate(content)
            if data.get("pattern_spec") is not None:
                data["pattern_spec"] = PatternSpec.model_validate(
                    data["pattern_spec"]
                ).model_dump(mode="json")
        elif node_type == "table":
            if data.get("table_spec") is None and content not in (
                None,
                "",
                {"blocks": []},
            ):
                raw_table_spec = content
                if isinstance(raw_table_spec, str):
                    raw_table_spec = TableSpec.model_validate_json(raw_table_spec)
                else:
                    raw_table_spec = TableSpec.model_validate(raw_table_spec)
                data["table_spec"] = (
                    raw_table_spec.model_dump(mode="json")
                    if isinstance(raw_table_spec, TableSpec)
                    else raw_table_spec
                )
                data["content"] = NodeContent().model_dump(mode="json")
            else:
                data["content"] = NodeContent.model_validate(content)
            if data.get("table_spec") is not None:
                data["table_spec"] = TableSpec.model_validate(
                    data["table_spec"]
                ).model_dump(mode="json")
        elif node_type == "icon":
            data["content"] = NodeContent.model_validate(content)
        else:
            data["content"] = NodeContent.model_validate(content)

        return data

    @model_validator(mode="after")
    def validate_node_type_specific_fields(self) -> Node:
        icon_fields_present = any(
            value is not None
            for value in (self.icon_name, self.x, self.y, self.size, self.color)
        )
        if self.type == "text":
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if self.image_path is not None:
                raise ValueError("text nodes cannot define image_path")
            if self.chart_spec is not None:
                raise ValueError("text nodes cannot define chart_spec")
            if self.shape_spec is not None:
                raise ValueError("text nodes cannot define shape_spec")
            if self.table_spec is not None:
                raise ValueError("text nodes cannot define table_spec")
            if self.pattern_spec is not None:
                raise ValueError("text nodes cannot define pattern_spec")
            if icon_fields_present:
                raise ValueError("text nodes cannot define icon placement fields")
            if icon_fields_present:
                raise ValueError("text nodes cannot define icon placement fields")
            return self

        if self.type == "image":
            if self.chart_spec is not None:
                raise ValueError("image nodes cannot define chart_spec")
            if self.shape_spec is not None:
                raise ValueError("image nodes cannot define shape_spec")
            if self.table_spec is not None:
                raise ValueError("image nodes cannot define table_spec")
            if self.pattern_spec is not None:
                raise ValueError("image nodes cannot define pattern_spec")
            if icon_fields_present:
                raise ValueError("image nodes cannot define icon placement fields")
            if not self.image_path:
                if self.style_overrides.get("placeholder"):
                    return self
                raise ValueError("image nodes require image_path")
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if not self.content.is_empty():
                raise ValueError("image nodes cannot define text content")
            self.image_path = self.image_path.strip()
            return self

        if self.type == "icon":
            if self.slot_binding is not None:
                raise ValueError("icon nodes cannot define slot_binding")
            if self.image_path is not None:
                raise ValueError("icon nodes cannot define image_path")
            if self.chart_spec is not None:
                raise ValueError("icon nodes cannot define chart_spec")
            if self.shape_spec is not None:
                raise ValueError("icon nodes cannot define shape_spec")
            if self.table_spec is not None:
                raise ValueError("icon nodes cannot define table_spec")
            if self.pattern_spec is not None:
                raise ValueError("icon nodes cannot define pattern_spec")
            if not self.content.is_empty():
                raise ValueError("icon nodes cannot define text content")
            if self.icon_name is None or not self.icon_name.strip():
                raise ValueError("icon nodes require icon_name")
            if not has_icon(self.icon_name):
                raise AgentSlidesError(INVALID_ICON, f"Unknown icon {self.icon_name!r}")
            if self.x is None or self.y is None:
                raise ValueError("icon nodes require x and y coordinates")
            if self.size is None or self.size <= 0:
                raise ValueError("icon nodes require a positive size")
            self.icon_name = self.icon_name.strip()
            self.color = normalize_hex_color(self.color or "#000000")
            return self

        if self.type == "shape":
            if self.slot_binding is not None:
                raise ValueError("shape nodes cannot be bound to a slot")
            if self.image_path is not None:
                raise ValueError("shape nodes cannot define image_path")
            if self.chart_spec is not None:
                raise ValueError("shape nodes cannot define chart_spec")
            if self.table_spec is not None:
                raise ValueError("shape nodes cannot define table_spec")
            if self.pattern_spec is not None:
                raise ValueError("shape nodes cannot define pattern_spec")
            if icon_fields_present:
                raise ValueError("shape nodes cannot define icon placement fields")
            if self.shape_spec is None:
                raise ValueError("shape nodes require shape_spec")
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if not self.content.is_empty():
                raise ValueError("shape nodes cannot define text content")
            for key in ("x", "y", "width", "height"):
                value = self.style_overrides.get(key)
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise ValueError(
                        f"shape nodes require numeric style_overrides['{key}']"
                    )
            z_index = self.style_overrides.get("z_index")
            if z_index is not None and (
                isinstance(z_index, bool) or not isinstance(z_index, int)
            ):
                raise ValueError(
                    "shape nodes require integer style_overrides['z_index'] when provided"
                )
            return self

        if self.type == "chart":
            if self.image_path is not None:
                raise ValueError("chart nodes cannot define image_path")
            if self.shape_spec is not None:
                raise ValueError("chart nodes cannot define shape_spec")
            if self.table_spec is not None:
                raise ValueError("chart nodes cannot define table_spec")
            if self.pattern_spec is not None:
                raise ValueError("chart nodes cannot define pattern_spec")
            if icon_fields_present:
                raise ValueError("chart nodes cannot define icon placement fields")
            if self.chart_spec is None:
                raise ValueError("chart nodes require chart_spec")
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if not self.content.is_empty():
                raise ValueError("chart nodes cannot define text content")
            return self

        if self.type == "pattern":
            if self.slot_binding is None:
                raise ValueError("pattern nodes require slot_binding")
            if self.image_path is not None:
                raise ValueError("pattern nodes cannot define image_path")
            if self.chart_spec is not None:
                raise ValueError("pattern nodes cannot define chart_spec")
            if self.shape_spec is not None:
                raise ValueError("pattern nodes cannot define shape_spec")
            if self.table_spec is not None:
                raise ValueError("pattern nodes cannot define table_spec")
            if self.pattern_spec is None:
                raise ValueError("pattern nodes require pattern_spec")
            if icon_fields_present:
                raise ValueError("pattern nodes cannot define icon placement fields")
            if not isinstance(self.content, NodeContent):
                self.content = NodeContent.model_validate(self.content)
            if not self.content.is_empty():
                raise ValueError("pattern nodes cannot define text content")
            return self

        if self.type != "table":
            raise ValueError(f"unsupported node type: {self.type}")
        if self.image_path is not None:
            raise ValueError("table nodes cannot define image_path")
        if self.chart_spec is not None:
            raise ValueError("table nodes cannot define chart_spec")
        if icon_fields_present:
            raise ValueError("table nodes cannot define icon placement fields")
        if self.shape_spec is not None:
            raise ValueError("table nodes cannot define shape_spec")
        if self.pattern_spec is not None:
            raise ValueError("table nodes cannot define pattern_spec")
        if self.table_spec is None:
            raise ValueError("table nodes require table_spec")
        if not isinstance(self.content, NodeContent):
            self.content = NodeContent.model_validate(self.content)
        if not self.content.is_empty():
            raise ValueError("table nodes cannot define text content")
        return self


class Slide(AgentSlidesModel):
    slide_id: str
    layout: str
    revision: int = 0
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
    peer_group: str | None = None
    alignment_group: str | None = None
    reading_order: int = 0
    size_policy: str = "fixed"
    allowed_content: list[str] = Field(
        default_factory=lambda: ["text", "image", "chart", "table", "icon", "pattern"]
    )
    min_font: float | None = None
    max_font: float | None = None
    preferred_font: float | None = None
    text_align: str = "left"
    vertical_align: SlotVerticalAlign = "top"
    full_bleed: bool = False
    padding: float = 8.0
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    bg_color: str | None = None
    bg_transparency: float = 0.0
    height_mode: ConstraintHeightMode = "fixed"
    width_mode: ConstraintWidthMode = "fixed"

    @field_validator("bg_transparency")
    @classmethod
    def validate_bg_transparency(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("bg_transparency must be between 0.0 and 1.0")
        return value

    @field_validator("padding")
    @classmethod
    def validate_padding(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("padding must be greater than or equal to 0.0")
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
    ladder: list[float] | None = None


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
    revision: int = 0
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
                    revision=slide.revision,
                    computed=slide.computed,
                )
                for slide in deck.slides
            ],
        )

    def apply_to_deck(self, deck: Deck) -> None:
        for slide in deck.slides:
            slide.revision = 0
            slide.computed = {}

        if self.deck_id != deck.deck_id or self.revision != deck.revision:
            return

        slides_by_id = {slide.slide_id: slide for slide in deck.slides}
        for computed_slide in self.slides:
            slide = slides_by_id.get(computed_slide.slide_id)
            if slide is None:
                continue
            slide.revision = computed_slide.revision
            slide.computed = dict(computed_slide.computed)
