"""Pattern generation helpers for slot-bound freeform compositions."""

from __future__ import annotations

from math import ceil
from typing import Any

from agent_slides.model.types import ComputedPatternElement, PatternSpec, Theme


def _mix_hex_colors(base: str, overlay: str, ratio: float) -> str:
    base_rgb = [int(base.lstrip("#")[index : index + 2], 16) for index in (0, 2, 4)]
    overlay_rgb = [
        int(overlay.lstrip("#")[index : index + 2], 16) for index in (0, 2, 4)
    ]
    blended = [
        int(round((1.0 - ratio) * base_channel + ratio * overlay_channel))
        for base_channel, overlay_channel in zip(base_rgb, overlay_rgb, strict=True)
    ]
    return "#" + "".join(f"{channel:02X}" for channel in blended)


def _shape(
    *,
    shape_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    z_index: int = 0,
    fill_color: str | None = None,
    line_color: str | None = None,
    line_width: float = 0.0,
    corner_radius: float = 0.0,
    shadow: bool = False,
    dash: str | None = None,
    opacity: float = 1.0,
) -> ComputedPatternElement:
    return ComputedPatternElement(
        kind="shape",
        shape_type=shape_type,
        x=x,
        y=y,
        width=width,
        height=height,
        z_index=z_index,
        fill_color=fill_color,
        line_color=line_color,
        line_width=line_width,
        corner_radius=corner_radius,
        shadow=shadow,
        dash=dash,
        opacity=opacity,
    )


def _text(
    *,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size_pt: float,
    font_family: str,
    color: str,
    z_index: int = 1,
    font_bold: bool = False,
    text_align: str = "left",
    vertical_align: str = "top",
) -> ComputedPatternElement:
    return ComputedPatternElement(
        kind="text",
        text=text,
        x=x,
        y=y,
        width=width,
        height=height,
        z_index=z_index,
        font_size_pt=font_size_pt,
        font_family=font_family,
        color=color,
        font_bold=font_bold,
        text_align=text_align,
        vertical_align=vertical_align,
    )


def _require_list(data: object, *, field: str = "data") -> list[Any]:
    if not isinstance(data, list):
        raise ValueError(f"{field} must be a JSON array")
    return data


def _require_dict(data: object, *, field: str = "data") -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{field} must be a JSON object")
    return data


def _normalize_item(value: object, *, title_key: str = "title") -> dict[str, str]:
    if isinstance(value, str):
        return {title_key: value.strip()}
    if not isinstance(value, dict):
        raise ValueError("pattern items must be strings or objects")
    normalized: dict[str, str] = {}
    for key, raw in value.items():
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise ValueError(f"pattern field '{key}' must be a string")
        normalized[key] = raw.strip()
    return normalized


def pattern_item_count(spec: PatternSpec) -> int:
    data = spec.data
    if spec.pattern_type == "comparison-cards":
        if isinstance(data, list):
            return len(data)
        payload = _require_dict(data)
        count = 0
        if payload.get("left") is not None:
            count += 1
        if payload.get("right") is not None:
            count += 1
        return count
    if spec.pattern_type in {"process-flow", "chevron-flow"} and isinstance(data, dict):
        return len(_require_list(data.get("phases"), field="data.phases"))
    if isinstance(data, list):
        return len(data)
    return 1


def generate_pattern_elements(
    spec: PatternSpec,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    theme: Theme,
) -> list[ComputedPatternElement]:
    if width <= 0 or height <= 0:
        return []

    generators = {
        "kpi-row": _generate_kpi_row,
        "card-grid": _generate_card_grid,
        "process-flow": _generate_process_flow,
        "chevron-flow": _generate_chevron_flow,
        "comparison-cards": _generate_comparison_cards,
        "icon-row": _generate_icon_row,
    }
    return generators[spec.pattern_type](
        spec, x=x, y=y, width=width, height=height, theme=theme
    )


def _generate_kpi_row(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    items = [
        _normalize_item(item, title_key="value") for item in _require_list(spec.data)
    ]
    if len(items) < 2:
        raise ValueError("kpi-row requires at least 2 items")

    gap = min(theme.spacing.gutter, width * 0.04)
    tile_width = max((width - gap * (len(items) - 1)) / len(items), 24.0)
    card_fill = _mix_hex_colors(theme.colors.background, theme.colors.secondary, 0.12)
    border = _mix_hex_colors(theme.colors.background, theme.colors.primary, 0.28)
    subtle = theme.colors.subtle_text or theme.colors.text
    inset = max(theme.spacing.base_unit, 10.0)
    value_size = max(22.0, min(34.0, height * 0.24))
    label_size = max(11.0, min(15.0, value_size * 0.44))
    detail_size = max(10.0, label_size - 1.0)

    elements: list[ComputedPatternElement] = []
    for index, item in enumerate(items):
        card_x = x + index * (tile_width + gap)
        elements.append(
            _shape(
                shape_type="rounded_rectangle",
                x=card_x,
                y=y,
                width=tile_width,
                height=height,
                fill_color=card_fill,
                line_color=border,
                line_width=1.0,
                corner_radius=12.0,
                shadow=True,
            )
        )
        elements.append(
            _text(
                text=item.get("value", ""),
                x=card_x + inset,
                y=y + inset,
                width=tile_width - inset * 2,
                height=height * 0.42,
                font_size_pt=value_size,
                font_family=theme.fonts.heading,
                color=theme.colors.primary,
                font_bold=True,
            )
        )
        elements.append(
            _text(
                text=item.get("label", ""),
                x=card_x + inset,
                y=y + height * 0.54,
                width=tile_width - inset * 2,
                height=height * 0.18,
                font_size_pt=label_size,
                font_family=theme.fonts.body,
                color=subtle,
                font_bold=True,
            )
        )
        detail = item.get("detail")
        if detail:
            elements.append(
                _text(
                    text=detail,
                    x=card_x + inset,
                    y=y + height * 0.72,
                    width=tile_width - inset * 2,
                    height=height * 0.16,
                    font_size_pt=detail_size,
                    font_family=theme.fonts.body,
                    color=theme.colors.text,
                )
            )
    return elements


def _generate_card_grid(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    items = [_normalize_item(item) for item in _require_list(spec.data)]
    if len(items) < 2:
        raise ValueError("card-grid requires at least 2 items")

    columns = spec.columns or min(3, len(items))
    rows = ceil(len(items) / columns)
    gap_x = min(theme.spacing.gutter, width * 0.04)
    gap_y = min(theme.spacing.gutter, height * 0.08)
    card_width = max((width - gap_x * (columns - 1)) / columns, 24.0)
    card_height = max((height - gap_y * (rows - 1)) / rows, 24.0)
    card_fill = _mix_hex_colors(theme.colors.background, theme.colors.secondary, 0.08)
    border = _mix_hex_colors(theme.colors.background, theme.colors.primary, 0.2)
    title_size = max(16.0, min(22.0, card_height * 0.16))
    body_size = max(11.0, min(14.0, title_size * 0.68))
    inset = max(theme.spacing.base_unit, 10.0)

    elements: list[ComputedPatternElement] = []
    for index, item in enumerate(items):
        row = index // columns
        column = index % columns
        card_x = x + column * (card_width + gap_x)
        card_y = y + row * (card_height + gap_y)
        elements.append(
            _shape(
                shape_type="rounded_rectangle",
                x=card_x,
                y=card_y,
                width=card_width,
                height=card_height,
                fill_color=card_fill,
                line_color=border,
                line_width=1.0,
                corner_radius=12.0,
                shadow=True,
            )
        )
        elements.append(
            _shape(
                shape_type="rectangle",
                x=card_x,
                y=card_y,
                width=6.0,
                height=card_height,
                fill_color=theme.colors.primary,
                opacity=0.9,
            )
        )
        elements.append(
            _text(
                text=item.get("title", ""),
                x=card_x + inset + 6.0,
                y=card_y + inset,
                width=card_width - inset * 2 - 6.0,
                height=card_height * 0.22,
                font_size_pt=title_size,
                font_family=theme.fonts.heading,
                color=theme.colors.primary,
                font_bold=True,
            )
        )
        elements.append(
            _text(
                text=item.get("body", ""),
                x=card_x + inset + 6.0,
                y=card_y + inset + card_height * 0.22,
                width=card_width - inset * 2 - 6.0,
                height=card_height - inset * 2 - card_height * 0.22,
                font_size_pt=body_size,
                font_family=theme.fonts.body,
                color=theme.colors.text,
            )
        )
    return elements


def _generate_process_flow(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    payload = _require_dict(spec.data)
    phases = [
        _normalize_item(item, title_key="title")
        for item in _require_list(payload.get("phases"), field="data.phases")
    ]
    if len(phases) < 3:
        raise ValueError("process-flow requires at least 3 phases")

    gap = min(theme.spacing.gutter, width * 0.03)
    card_width = max((width - gap * (len(phases) - 1)) / len(phases), 24.0)
    card_height = height * 0.62
    card_y = y + height * 0.28
    inset = max(theme.spacing.base_unit, 10.0)
    title_size = max(15.0, min(20.0, card_height * 0.15))
    body_size = max(10.0, min(13.0, title_size * 0.68))
    card_fill = _mix_hex_colors(theme.colors.background, theme.colors.secondary, 0.08)
    border = _mix_hex_colors(theme.colors.background, theme.colors.primary, 0.22)

    elements: list[ComputedPatternElement] = []
    for index, phase in enumerate(phases):
        card_x = x + index * (card_width + gap)
        badge_size = min(28.0, height * 0.16)
        badge_x = card_x
        badge_y = y + height * 0.04
        elements.append(
            _shape(
                shape_type="oval",
                x=badge_x,
                y=badge_y,
                width=badge_size,
                height=badge_size,
                fill_color=theme.colors.primary,
                line_color=theme.colors.primary,
                line_width=1.0,
            )
        )
        elements.append(
            _text(
                text=str(index + 1),
                x=badge_x,
                y=badge_y + 2.0,
                width=badge_size,
                height=badge_size - 4.0,
                font_size_pt=max(12.0, badge_size * 0.42),
                font_family=theme.fonts.heading,
                color="#FFFFFF",
                font_bold=True,
                text_align="center",
                vertical_align="middle",
            )
        )
        if index < len(phases) - 1:
            line_y = card_y + card_height * 0.34
            elements.append(
                _shape(
                    shape_type="line",
                    x=card_x + card_width,
                    y=line_y,
                    width=gap,
                    height=0.0,
                    z_index=0,
                    line_color=_mix_hex_colors(
                        theme.colors.background, theme.colors.primary, 0.45
                    ),
                    line_width=1.5,
                    dash="dash",
                )
            )
        elements.append(
            _shape(
                shape_type="rounded_rectangle",
                x=card_x,
                y=card_y,
                width=card_width,
                height=card_height,
                fill_color=card_fill,
                line_color=border,
                line_width=1.0,
                corner_radius=10.0,
                shadow=True,
            )
        )
        elements.append(
            _text(
                text=phase.get("title", ""),
                x=card_x + inset,
                y=card_y + inset,
                width=card_width - inset * 2,
                height=card_height * 0.22,
                font_size_pt=title_size,
                font_family=theme.fonts.heading,
                color=theme.colors.primary,
                font_bold=True,
            )
        )
        body = phase.get("body") or phase.get("label", "")
        if body:
            elements.append(
                _text(
                    text=body,
                    x=card_x + inset,
                    y=card_y + inset + card_height * 0.2,
                    width=card_width - inset * 2,
                    height=card_height - inset * 2 - card_height * 0.2,
                    font_size_pt=body_size,
                    font_family=theme.fonts.body,
                    color=theme.colors.text,
                )
            )
    return elements


def _generate_chevron_flow(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    payload = spec.data if isinstance(spec.data, dict) else {"phases": spec.data}
    phases = [
        _normalize_item(item, title_key="label")
        for item in _require_list(payload.get("phases"), field="data.phases")
    ]
    if len(phases) < 3:
        raise ValueError("chevron-flow requires at least 3 phases")

    gap = min(4.0, width * 0.005)
    chevron_width = max((width - gap * (len(phases) - 1)) / len(phases), 24.0)
    fill_palette = [
        theme.colors.primary,
        _mix_hex_colors(theme.colors.primary, theme.colors.accent, 0.45),
        theme.colors.accent,
        _mix_hex_colors(theme.colors.accent, theme.colors.secondary, 0.4),
    ]
    text_size = max(13.0, min(18.0, height * 0.16))
    elements: list[ComputedPatternElement] = []
    for index, phase in enumerate(phases):
        chevron_x = x + index * (chevron_width + gap)
        elements.append(
            _shape(
                shape_type="chevron",
                x=chevron_x,
                y=y,
                width=chevron_width,
                height=height,
                fill_color=fill_palette[index % len(fill_palette)],
                line_color=_mix_hex_colors(
                    theme.colors.background,
                    fill_palette[index % len(fill_palette)],
                    0.2,
                ),
                line_width=1.0,
            )
        )
        elements.append(
            _text(
                text=phase.get("label", phase.get("title", "")),
                x=chevron_x + chevron_width * 0.14,
                y=y + height * 0.14,
                width=chevron_width * 0.62,
                height=height * 0.72,
                font_size_pt=text_size,
                font_family=theme.fonts.heading,
                color="#FFFFFF",
                font_bold=True,
                text_align="center",
                vertical_align="middle",
            )
        )
    return elements


def _generate_comparison_cards(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    if isinstance(spec.data, list):
        items = [_normalize_item(item) for item in spec.data]
        if len(items) != 2:
            raise ValueError("comparison-cards list input requires exactly 2 items")
        left, right = items
        arrow_label = "vs."
    else:
        payload = _require_dict(spec.data)
        left = _normalize_item(payload.get("left", {}))
        right = _normalize_item(payload.get("right", {}))
        arrow_label = str(payload.get("arrow_label") or "vs.")

    gap = min(theme.spacing.gutter * 1.2, width * 0.08)
    card_width = max((width - gap) / 2, 24.0)
    inset = max(theme.spacing.base_unit, 10.0)
    title_size = max(17.0, min(23.0, height * 0.14))
    body_size = max(11.0, min(14.0, title_size * 0.68))
    left_fill = _mix_hex_colors(theme.colors.background, theme.colors.secondary, 0.08)
    right_fill = _mix_hex_colors(theme.colors.background, theme.colors.accent, 0.1)
    border = _mix_hex_colors(theme.colors.background, theme.colors.primary, 0.18)
    arrow_y = y + height * 0.44

    elements = [
        _shape(
            shape_type="rounded_rectangle",
            x=x,
            y=y,
            width=card_width,
            height=height,
            fill_color=left_fill,
            line_color=border,
            line_width=1.0,
            corner_radius=12.0,
            shadow=True,
        ),
        _shape(
            shape_type="rounded_rectangle",
            x=x + card_width + gap,
            y=y,
            width=card_width,
            height=height,
            fill_color=right_fill,
            line_color=border,
            line_width=1.0,
            corner_radius=12.0,
            shadow=True,
        ),
        _shape(
            shape_type="arrow",
            x=x + card_width + gap * 0.2,
            y=arrow_y,
            width=gap * 0.6,
            height=max(24.0, height * 0.12),
            fill_color=theme.colors.primary,
            line_color=theme.colors.primary,
        ),
        _text(
            text=arrow_label,
            x=x + card_width,
            y=arrow_y - height * 0.12,
            width=gap,
            height=height * 0.18,
            font_size_pt=max(11.0, body_size),
            font_family=theme.fonts.body,
            color=theme.colors.subtle_text or theme.colors.text,
            font_bold=True,
            text_align="center",
            vertical_align="middle",
        ),
    ]

    for card_x, payload, accent in (
        (x, left, theme.colors.primary),
        (x + card_width + gap, right, theme.colors.accent),
    ):
        elements.append(
            _text(
                text=payload.get("title", ""),
                x=card_x + inset,
                y=y + inset,
                width=card_width - inset * 2,
                height=height * 0.2,
                font_size_pt=title_size,
                font_family=theme.fonts.heading,
                color=accent,
                font_bold=True,
            )
        )
        body = payload.get("body", "")
        elements.append(
            _text(
                text=body,
                x=card_x + inset,
                y=y + inset + height * 0.18,
                width=card_width - inset * 2,
                height=height * 0.56,
                font_size_pt=body_size,
                font_family=theme.fonts.body,
                color=theme.colors.text,
            )
        )
        caption = payload.get("caption")
        if caption:
            elements.append(
                _text(
                    text=caption,
                    x=card_x + inset,
                    y=y + height * 0.8,
                    width=card_width - inset * 2,
                    height=height * 0.12,
                    font_size_pt=max(10.0, body_size - 1.0),
                    font_family=theme.fonts.body,
                    color=theme.colors.subtle_text or theme.colors.text,
                    font_bold=True,
                )
            )
    return elements


def _generate_icon_row(
    spec: PatternSpec, *, x: float, y: float, width: float, height: float, theme: Theme
) -> list[ComputedPatternElement]:
    items = [_normalize_item(item) for item in _require_list(spec.data)]
    if len(items) < 2:
        raise ValueError("icon-row requires at least 2 items")

    gap = min(theme.spacing.gutter, width * 0.04)
    card_width = max((width - gap * (len(items) - 1)) / len(items), 24.0)
    circle = min(card_width * 0.42, height * 0.24)
    title_size = max(13.0, min(18.0, height * 0.12))
    body_size = max(10.0, min(13.0, title_size * 0.74))
    subtle = theme.colors.subtle_text or theme.colors.text

    elements: list[ComputedPatternElement] = []
    for index, item in enumerate(items):
        item_x = x + index * (card_width + gap)
        circle_x = item_x + (card_width - circle) / 2
        circle_y = y
        icon = item.get("icon") or (item.get("title", "?")[:1].upper() or "?")
        elements.append(
            _shape(
                shape_type="oval",
                x=circle_x,
                y=circle_y,
                width=circle,
                height=circle,
                fill_color=_mix_hex_colors(
                    theme.colors.background, theme.colors.secondary, 0.08
                ),
                line_color=theme.colors.primary,
                line_width=1.4,
            )
        )
        elements.append(
            _text(
                text=icon,
                x=circle_x,
                y=circle_y + 2.0,
                width=circle,
                height=circle - 4.0,
                font_size_pt=max(14.0, circle * 0.38),
                font_family=theme.fonts.heading,
                color=theme.colors.primary,
                font_bold=True,
                text_align="center",
                vertical_align="middle",
            )
        )
        elements.append(
            _text(
                text=item.get("label") or item.get("title", ""),
                x=item_x,
                y=y + circle + max(theme.spacing.base_unit, 8.0),
                width=card_width,
                height=height * 0.16,
                font_size_pt=title_size,
                font_family=theme.fonts.heading,
                color=theme.colors.primary,
                font_bold=True,
                text_align="center",
                vertical_align="middle",
            )
        )
        elements.append(
            _text(
                text=item.get("body", ""),
                x=item_x,
                y=y + circle + max(theme.spacing.base_unit, 8.0) + height * 0.15,
                width=card_width,
                height=max(
                    0.0,
                    height - circle - height * 0.15 - max(theme.spacing.base_unit, 8.0),
                ),
                font_size_pt=body_size,
                font_family=theme.fonts.body,
                color=subtle,
                text_align="center",
            )
        )
    return elements
