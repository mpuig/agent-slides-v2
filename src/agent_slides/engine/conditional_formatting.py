"""Shared conditional-formatting helpers for text, charts, and tables."""

from __future__ import annotations

import re

from agent_slides.model.design_rules import (
    ConditionalFormatting,
    ConditionalRule,
    DesignRules,
)
from agent_slides.model.types import ChartSpec, TextBlock, TextRun

POSITIVE_NUMBER_PATTERN = re.compile(
    r"(?<!\w)\+\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:%|x|bp|bps|k|m|mm|bn|t))?(?!\w)",
    re.IGNORECASE,
)
NEGATIVE_NUMBER_PATTERN = re.compile(
    r"(?<!\w)-\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:%|x|bp|bps|k|m|mm|bn|t))?(?!\w)",
    re.IGNORECASE,
)


def _merge_adjacent_runs(runs: list[TextRun]) -> list[TextRun]:
    merged: list[TextRun] = []
    for run in runs:
        if run.text == "":
            continue
        if not merged:
            merged.append(run)
            continue
        previous = merged[-1]
        if (
            previous.bold == run.bold
            and previous.italic == run.italic
            and previous.color == run.color
            and previous.font_size == run.font_size
            and previous.underline == run.underline
            and previous.strikethrough == run.strikethrough
        ):
            merged[-1] = previous.model_copy(update={"text": previous.text + run.text})
            continue
        merged.append(run)
    return merged


def _rule_pattern(rule: ConditionalRule) -> re.Pattern[str]:
    if rule.pattern == "positive_number":
        return POSITIVE_NUMBER_PATTERN
    if rule.pattern == "negative_number":
        return NEGATIVE_NUMBER_PATTERN
    return re.compile(re.escape(rule.match or ""), re.IGNORECASE)


def _overlay_run_style(run: TextRun, rule: ConditionalRule) -> TextRun:
    payload: dict[str, object] = {}
    if run.color is None:
        payload["color"] = rule.color
    if rule.bold and run.bold is None:
        payload["bold"] = True
    return run.model_copy(update=payload) if payload else run


def _apply_rule_to_runs(runs: list[TextRun], rule: ConditionalRule) -> list[TextRun]:
    matcher = _rule_pattern(rule)
    formatted: list[TextRun] = []
    for run in runs:
        if not run.text:
            formatted.append(run)
            continue
        last_index = 0
        matched = False
        for match in matcher.finditer(run.text):
            start, end = match.span()
            if start == end:
                continue
            matched = True
            if start > last_index:
                formatted.append(
                    run.model_copy(update={"text": run.text[last_index:start]})
                )
            formatted.append(
                _overlay_run_style(
                    run.model_copy(update={"text": run.text[start:end]}), rule
                )
            )
            last_index = end
        if not matched:
            formatted.append(run)
            continue
        if last_index < len(run.text):
            formatted.append(run.model_copy(update={"text": run.text[last_index:]}))
    return _merge_adjacent_runs(formatted)


def resolved_text_runs(
    block: TextBlock,
    conditional_formatting: ConditionalFormatting | None,
) -> list[TextRun]:
    """Return text runs with conditional formatting applied on top of authored runs."""

    runs = block.resolved_runs()
    if conditional_formatting is None:
        return runs
    for rule in conditional_formatting.text_rules:
        runs = _apply_rule_to_runs(runs, rule)
    return _merge_adjacent_runs(runs) or [TextRun(text="")]


def _single_series_values(chart_spec: ChartSpec | None) -> list[float] | None:
    if chart_spec is None or chart_spec.chart_type == "scatter":
        return None
    if not chart_spec.series or len(chart_spec.series) != 1:
        return None
    return list(chart_spec.series[0].values)


def resolve_chart_point_colors(
    chart_spec: ChartSpec | None,
    conditional_formatting: ConditionalFormatting | None,
) -> list[str] | None:
    """Return per-point colors for charts that use conditional point coloring."""

    if chart_spec is None:
        return None
    values = _single_series_values(chart_spec)
    if values is None:
        return None

    style = chart_spec.style
    chart_rules = (
        conditional_formatting.chart if conditional_formatting is not None else None
    )
    if style.highlight_index is not None:
        highlight_color = style.highlight_color or (
            chart_rules.highlight_color if chart_rules else "#C98E48"
        )
        muted_color = style.muted_color or (
            chart_rules.muted_color if chart_rules else "#CFC8BD"
        )
        return [
            highlight_color if index == style.highlight_index else muted_color
            for index in range(len(values))
        ]

    if style.color_by_value:
        positive_color = chart_rules.positive_color if chart_rules else "#1B8A2D"
        negative_color = chart_rules.negative_color if chart_rules else "#D32F2F"
        return [positive_color if value >= 0 else negative_color for value in values]

    return None


def resolve_table_cell_style(
    value: str,
    *,
    default_fill: str,
    default_text: str,
    conditional_formatting: ConditionalFormatting | None,
) -> tuple[str, str, bool]:
    """Resolve table cell fill/text colors for semantic status values."""

    if conditional_formatting is None:
        return default_fill, default_text, False

    normalized = value.strip().casefold()
    if not normalized:
        return default_fill, default_text, False

    status_style = conditional_formatting.table.statuses.get(normalized)
    if status_style is None:
        return default_fill, default_text, False
    return status_style.fill, status_style.text, status_style.bold


def preview_conditional_formatting_payload(
    design_rules: DesignRules,
) -> dict[str, object]:
    """Serialize only the preview-relevant conditional-formatting settings."""

    return design_rules.conditional_formatting.model_dump(mode="json")
