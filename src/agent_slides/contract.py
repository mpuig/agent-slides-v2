"""Canonical command and tool contract for agent-slides."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_slides.errors import (
    CHART_DATA_ERROR,
    FILE_EXISTS,
    FILE_NOT_FOUND,
    INVALID_CHART_TYPE,
    INVALID_ICON,
    INVALID_LAYOUT,
    INVALID_NODE_TYPE,
    INVALID_SLIDE,
    INVALID_SLOT,
    INVALID_TOOL_INPUT,
    INVALID_TOOL_NAME,
    OVERFLOW,
    REVISION_CONFLICT,
    SCHEMA_ERROR,
    SLOT_OCCUPIED,
    TEMPLATE_CHANGED,
    THEME_INVALID,
    THEME_NOT_FOUND,
    THEME_ROLE_NOT_FOUND,
    UNBOUND_NODES,
)
from agent_slides.model import Deck, NodeContent, TableSpec
from agent_slides.model.constraints import Constraint
from agent_slides.model.types import (
    CHART_TYPE_VALUES,
    PATTERN_TYPE_VALUES,
    SHAPE_DASH_VALUES,
    SHAPE_TYPE_VALUES,
)

CONTRACT_VERSION = 1

LEGACY_ORCHESTRATOR_PROFILE = "legacy_orchestrator"
PREVIEW_CHAT_PROFILE = "preview_chat"

MUTATION_COMMAND_NAMES = (
    "slide_add",
    "slide_remove",
    "slide_set_layout",
    "slot_set",
    "slot_clear",
    "slot_bind",
    "chart_add",
    "chart_update",
    "icon_add",
    "shape_add",
    "table_add",
    "pattern_add",
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _string_schema(*, min_length: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if min_length is not None:
        schema["minLength"] = min_length
    return schema


def _number_schema() -> dict[str, Any]:
    return {"type": "number"}


def _integer_schema(
    *, minimum: int | None = None, default: int | None = None
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    if default is not None:
        schema["default"] = default
    return schema


def _boolean_schema(*, default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean"}
    if default is not None:
        schema["default"] = default
    return schema


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
    description: str | None = None,
    any_of: list[dict[str, Any]] | None = None,
    one_of: list[dict[str, Any]] | None = None,
    all_of: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    if description:
        schema["description"] = description
    if any_of:
        schema["anyOf"] = any_of
    if one_of:
        schema["oneOf"] = one_of
    if all_of:
        schema["allOf"] = all_of
    return schema


def _array_schema(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _success_envelope(data_schema: dict[str, Any]) -> dict[str, Any]:
    return _object_schema(
        {
            "ok": {"const": True},
            "data": data_schema,
        },
        required=["ok", "data"],
    )


def _error_envelope() -> dict[str, Any]:
    return _object_schema(
        {
            "ok": {"const": False},
            "error": _object_schema(
                {
                    "code": _string_schema(min_length=1),
                    "message": _string_schema(min_length=1),
                },
                required=["code", "message"],
                additional_properties=True,
            ),
        },
        required=["ok", "error"],
    )


def _cli_command(*path: str) -> str:
    return " ".join(path)


DEFINITIONS: dict[str, Any] = {
    "deck": Deck.model_json_schema(),
    "structured_text": NodeContent.model_json_schema(),
    "validation_warning": Constraint.model_json_schema(),
    "slide_ref": {
        "anyOf": [
            {"type": "integer"},
            {"type": "string", "minLength": 1},
        ]
    },
    "slide_add_result": _object_schema(
        {
            "slide_index": _integer_schema(minimum=0),
            "slide_id": _string_schema(min_length=1),
            "layout": _string_schema(min_length=1),
            "auto_selected": _boolean_schema(),
            "reason": _string_schema(min_length=1),
        },
        required=["slide_index", "slide_id", "layout"],
    ),
    "slide_remove_result": _object_schema(
        {
            "removed": _string_schema(min_length=1),
            "slide_count": _integer_schema(minimum=0),
        },
        required=["removed", "slide_count"],
    ),
    "slide_set_layout_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "layout": _string_schema(min_length=1),
            "unbound_nodes": _array_schema(_string_schema(min_length=1)),
        },
        required=["slide_id", "layout", "unbound_nodes"],
    ),
    "slide_set_layout_warning": _success_envelope(
        _object_schema(
            {
                "slide_id": _string_schema(min_length=1),
                "unbound_nodes": _array_schema(_string_schema(min_length=1)),
            },
            required=["slide_id", "unbound_nodes"],
        )
    ),
    "slot_set_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "type": _string_schema(min_length=1),
            "text": _string_schema(),
            "content": _ref("structured_text"),
            "image_path": {"type": ["string", "null"]},
            "image_fit": _string_schema(min_length=1),
            "font_size": {"type": ["number", "null"]},
        },
        required=[
            "slide_id",
            "slot",
            "node_id",
            "type",
            "text",
            "content",
            "image_path",
            "image_fit",
            "font_size",
        ],
    ),
    "slot_clear_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "removed_node_ids": _array_schema(_string_schema(min_length=1)),
        },
        required=["slide_id", "slot", "removed_node_ids"],
    ),
    "slot_bind_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
        },
        required=["slide_id", "slot", "node_id"],
    ),
    "chart_add_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "chart_type": {"type": "string", "enum": list(CHART_TYPE_VALUES)},
        },
        required=["slide_id", "slot", "node_id", "chart_type"],
    ),
    "chart_update_result": _object_schema(
        {
            "node_id": _string_schema(min_length=1),
            "chart_type": {"type": "string", "enum": list(CHART_TYPE_VALUES)},
            "updated": {"const": True},
        },
        required=["node_id", "chart_type", "updated"],
    ),
    "icon_add_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "name": _string_schema(min_length=1),
            "x": _number_schema(),
            "y": _number_schema(),
            "size": _number_schema(),
            "color": _string_schema(min_length=4),
        },
        required=["slide_id", "node_id", "name", "x", "y", "size", "color"],
    ),
    "icon_list_result": _object_schema(
        {
            "icons": _array_schema(_string_schema(min_length=1)),
            "count": _integer_schema(minimum=0),
        },
        required=["icons", "count"],
    ),
    "shape_add_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "shape_type": {"type": "string", "enum": list(SHAPE_TYPE_VALUES)},
            "x": _number_schema(),
            "y": _number_schema(),
            "w": _number_schema(),
            "h": _number_schema(),
            "fill_color": {"type": ["string", "null"]},
            "line_color": {"type": ["string", "null"]},
            "line_width": _number_schema(),
            "corner_radius": _number_schema(),
            "shadow": _boolean_schema(),
            "dash": {"type": ["string", "null"], "enum": [*SHAPE_DASH_VALUES, None]},
            "opacity": _number_schema(),
            "z_index": {"type": "integer"},
        },
        required=[
            "slide_id",
            "node_id",
            "shape_type",
            "x",
            "y",
            "w",
            "h",
            "fill_color",
            "line_color",
            "line_width",
            "corner_radius",
            "shadow",
            "dash",
            "opacity",
            "z_index",
        ],
    ),
    "table_add_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "column_count": _integer_schema(minimum=1),
            "row_count": _integer_schema(minimum=0),
        },
        required=["slide_id", "slot", "node_id", "column_count", "row_count"],
    ),
    "pattern_add_result": _object_schema(
        {
            "slide_id": _string_schema(min_length=1),
            "slot": _string_schema(min_length=1),
            "node_id": _string_schema(min_length=1),
            "pattern_type": {"type": "string", "enum": list(PATTERN_TYPE_VALUES)},
            "item_count": _integer_schema(minimum=1),
        },
        required=["slide_id", "slot", "node_id", "pattern_type", "item_count"],
    ),
    "chart_data": _object_schema(
        {
            "title": {"type": ["string", "null"]},
            "categories": _array_schema(_string_schema()),
            "series": _array_schema(
                _object_schema(
                    {
                        "name": _string_schema(min_length=1),
                        "values": _array_schema(_number_schema()),
                    },
                    required=["name", "values"],
                )
            ),
            "scatter_series": _array_schema(
                _object_schema(
                    {
                        "name": _string_schema(min_length=1),
                        "points": _array_schema(
                            _object_schema(
                                {
                                    "x": _number_schema(),
                                    "y": _number_schema(),
                                },
                                required=["x", "y"],
                            )
                        ),
                    },
                    required=["name", "points"],
                )
            ),
            "style": _object_schema(
                {
                    "has_legend": _boolean_schema(),
                    "has_data_labels": _boolean_schema(),
                    "series_colors": _array_schema(_string_schema(min_length=1)),
                }
            ),
        },
        description="Chart payload accepted by chart_add and chart_update. Validation rules depend on the chart type.",
    ),
    "table_data": TableSpec.model_json_schema(),
    "pattern_data": {
        "anyOf": [
            {"type": "object", "additionalProperties": True},
            {"type": "array", "items": {}},
        ]
    },
    "build_result": _object_schema(
        {
            "output": _string_schema(min_length=1),
            "slides": _integer_schema(minimum=0),
        },
        required=["output", "slides"],
    ),
    "theme_list_result": _object_schema(
        {
            "themes": _array_schema(_string_schema(min_length=1)),
        },
        required=["themes"],
    ),
    "theme_apply_result": _object_schema(
        {
            "theme": _string_schema(min_length=1),
            "previous": _string_schema(min_length=1),
        },
        required=["theme", "previous"],
    ),
    "learn_result": _object_schema(
        {
            "source": _string_schema(min_length=1),
            "layouts_found": _integer_schema(minimum=0),
            "usable_layouts": _integer_schema(minimum=0),
        },
        required=["source", "layouts_found", "usable_layouts"],
    ),
    "inspect_result": _object_schema({}, additional_properties=True),
    "validate_result": _object_schema(
        {
            "warnings": _array_schema(_ref("validation_warning")),
            "clean": _boolean_schema(),
        },
        required=["warnings", "clean"],
    ),
    "batch_operation": _object_schema(
        {
            "command": {"type": "string", "enum": list(MUTATION_COMMAND_NAMES)},
            "args": _object_schema({}, additional_properties=True),
        },
        required=["command"],
    ),
    "batch_result": _object_schema(
        {
            "operations": _integer_schema(minimum=0),
            "results": _array_schema(
                {
                    "anyOf": [
                        _ref("slide_add_result"),
                        _ref("slide_remove_result"),
                        _ref("slide_set_layout_result"),
                        _ref("slot_set_result"),
                        _ref("slot_clear_result"),
                        _ref("slot_bind_result"),
                        _ref("chart_add_result"),
                        _ref("chart_update_result"),
                        _ref("icon_add_result"),
                        _ref("shape_add_result"),
                        _ref("table_add_result"),
                        _ref("pattern_add_result"),
                    ]
                }
            ),
        },
        required=["operations", "results"],
    ),
    "suggest_layout_result": _object_schema(
        {
            "suggestions": _array_schema(
                _object_schema({}, additional_properties=True)
            ),
        },
        required=["suggestions"],
    ),
    "server_started_result": _object_schema(
        {
            "url": _string_schema(min_length=1),
            "watching": _string_schema(min_length=1),
        },
        required=["url", "watching"],
    ),
    "server_stopped_result": _object_schema(
        {
            "stopped": {"const": True},
        },
        required=["stopped"],
    ),
    "tool_result_build": _object_schema(
        {
            "ok": {"const": True},
            "tool": {"const": "build"},
            "result": _ref("build_result"),
            "warnings": _array_schema(_ref("validation_warning")),
            "deck_revision": _integer_schema(minimum=0),
            "output_path": _string_schema(min_length=1),
            "download_url": _string_schema(min_length=1),
        },
        required=[
            "ok",
            "tool",
            "result",
            "warnings",
            "deck_revision",
            "output_path",
            "download_url",
        ],
    ),
    "tool_result_get_deck_info": _object_schema(
        {
            "ok": {"const": True},
            "deck": _ref("deck"),
        },
        required=["ok", "deck"],
    ),
    "tool_error": _object_schema(
        {
            "ok": {"const": False},
            "tool": _string_schema(min_length=1),
            "error": _object_schema(
                {
                    "code": _string_schema(min_length=1),
                    "message": _string_schema(min_length=1),
                },
                required=["code", "message"],
                additional_properties=True,
            ),
        },
        required=["ok", "tool", "error"],
    ),
}

ERROR_CONTRACTS: dict[str, dict[str, str]] = {
    INVALID_SLIDE: {
        "description": "The requested slide index or slide id does not exist."
    },
    INVALID_SLOT: {
        "description": "The requested slot name is not valid for the target layout."
    },
    INVALID_LAYOUT: {
        "description": "The requested layout is unknown for the active layout provider."
    },
    FILE_NOT_FOUND: {
        "description": "A required file, manifest, or asset could not be found."
    },
    SCHEMA_ERROR: {
        "description": "Input, JSON payload, or file structure validation failed."
    },
    OVERFLOW: {"description": "Rendered text overflowed its computed bounds."},
    UNBOUND_NODES: {
        "description": "A layout change left one or more nodes without a slot binding."
    },
    INVALID_CHART_TYPE: {"description": "The requested chart type is not supported."},
    INVALID_NODE_TYPE: {
        "description": "The requested node does not match the required node type."
    },
    REVISION_CONFLICT: {
        "description": "The deck revision changed unexpectedly during a write."
    },
    SLOT_OCCUPIED: {
        "description": "A slot could not be reused without discarding existing content."
    },
    FILE_EXISTS: {
        "description": "The target file already exists and force/overwrite was not enabled."
    },
    TEMPLATE_CHANGED: {
        "description": "The learned template changed and the stored manifest is stale."
    },
    CHART_DATA_ERROR: {
        "description": "Chart payload structure or values failed validation."
    },
    THEME_INVALID: {"description": "The requested theme definition is invalid."},
    THEME_NOT_FOUND: {"description": "The requested built-in theme does not exist."},
    THEME_ROLE_NOT_FOUND: {
        "description": "A referenced role is missing from the loaded theme."
    },
    INVALID_TOOL_INPUT: {
        "description": "An agent tool was called with a non-object input payload."
    },
    INVALID_TOOL_NAME: {
        "description": "An agent tool name is not part of the declared tool profile."
    },
    INVALID_ICON: {"description": "The requested built-in icon name does not exist."},
}

MUTATION_CONTRACTS: dict[str, dict[str, Any]] = {
    "slide_add": {
        "kind": "mutation",
        "summary": "Append a slide using either an explicit layout or an auto-selected layout.",
        "input_schema": _object_schema(
            {
                "layout": _string_schema(min_length=1),
                "auto_layout": _boolean_schema(default=False),
                "content": _ref("structured_text"),
                "image_count": _integer_schema(minimum=0, default=0),
            },
            all_of=[
                {
                    "if": {"properties": {"auto_layout": {"const": True}}},
                    "then": {"required": ["content"]},
                },
                {
                    "if": {"properties": {"auto_layout": {"const": False}}},
                    "then": {"required": ["layout"]},
                },
            ],
        ),
        "result_schema": _ref("slide_add_result"),
        "errors": [INVALID_LAYOUT, SCHEMA_ERROR],
    },
    "slide_remove": {
        "kind": "mutation",
        "summary": "Remove a slide by index or slide id.",
        "input_schema": _object_schema(
            {"slide": _ref("slide_ref")},
            required=["slide"],
        ),
        "result_schema": _ref("slide_remove_result"),
        "errors": [INVALID_SLIDE, SCHEMA_ERROR],
    },
    "slide_set_layout": {
        "kind": "mutation",
        "summary": "Change a slide layout and rebind any compatible slot content.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "layout": _string_schema(min_length=1),
            },
            required=["slide", "layout"],
        ),
        "result_schema": _ref("slide_set_layout_result"),
        "warnings": [UNBOUND_NODES],
        "errors": [INVALID_LAYOUT, INVALID_SLIDE, INVALID_SLOT, SCHEMA_ERROR],
    },
    "slot_set": {
        "kind": "mutation",
        "summary": "Set text, structured text, or an image into a slot on a slide.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "text": _string_schema(),
                "content": _ref("structured_text"),
                "image": _string_schema(min_length=1),
                "image_fit": {
                    "type": "string",
                    "enum": ["contain", "cover", "stretch"],
                },
                "font_size": {"type": "number"},
            },
            required=["slide", "slot"],
            one_of=[
                {"required": ["text"]},
                {"required": ["content"]},
                {"required": ["image"]},
            ],
        ),
        "result_schema": _ref("slot_set_result"),
        "errors": [FILE_NOT_FOUND, INVALID_SLIDE, INVALID_SLOT, SCHEMA_ERROR],
    },
    "slot_clear": {
        "kind": "mutation",
        "summary": "Remove all nodes currently bound to a slot on a slide.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
            },
            required=["slide", "slot"],
        ),
        "result_schema": _ref("slot_clear_result"),
        "errors": [INVALID_SLIDE, INVALID_SLOT, SCHEMA_ERROR],
    },
    "slot_bind": {
        "kind": "mutation",
        "summary": "Bind an existing node to a slot on its slide, pruning conflicting slot occupants.",
        "input_schema": _object_schema(
            {
                "node": _string_schema(min_length=1),
                "slot": _string_schema(min_length=1),
            },
            required=["node", "slot"],
        ),
        "result_schema": _ref("slot_bind_result"),
        "errors": [INVALID_SLOT, SCHEMA_ERROR],
    },
    "chart_add": {
        "kind": "mutation",
        "summary": "Insert or replace a chart node in a slot on a slide.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "type": {"type": "string", "enum": list(CHART_TYPE_VALUES)},
                "title": {"type": ["string", "null"]},
                "data": _ref("chart_data"),
            },
            required=["slide", "slot", "type", "data"],
        ),
        "result_schema": _ref("chart_add_result"),
        "errors": [
            CHART_DATA_ERROR,
            INVALID_CHART_TYPE,
            INVALID_SLIDE,
            INVALID_SLOT,
            SCHEMA_ERROR,
        ],
    },
    "chart_update": {
        "kind": "mutation",
        "summary": "Update the data payload for an existing chart node.",
        "input_schema": _object_schema(
            {
                "node": _string_schema(min_length=1),
                "data": _ref("chart_data"),
            },
            required=["node", "data"],
        ),
        "result_schema": _ref("chart_update_result"),
        "errors": [CHART_DATA_ERROR, INVALID_NODE_TYPE, SCHEMA_ERROR],
    },
    "icon_add": {
        "kind": "mutation",
        "summary": "Add a built-in icon node at absolute slide coordinates.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "name": _string_schema(min_length=1),
                "x": _number_schema(),
                "y": _number_schema(),
                "size": _number_schema(),
                "color": _string_schema(min_length=4),
            },
            required=["slide", "name", "x", "y", "size", "color"],
        ),
        "result_schema": _ref("icon_add_result"),
        "errors": [INVALID_ICON, INVALID_SLIDE, SCHEMA_ERROR],
    },
    "shape_add": {
        "kind": "mutation",
        "summary": "Add a slide-level decorative or structural shape with explicit coordinates.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "type": {"type": "string", "enum": list(SHAPE_TYPE_VALUES)},
                "x": _number_schema(),
                "y": _number_schema(),
                "w": _number_schema(),
                "h": _number_schema(),
                "fill": _string_schema(min_length=1),
                "color": _string_schema(min_length=1),
                "line_color": _string_schema(min_length=1),
                "line_width": _number_schema(),
                "corner_radius": _number_schema(),
                "shadow": _boolean_schema(default=False),
                "dash": {"type": "string", "enum": list(SHAPE_DASH_VALUES)},
                "opacity": _number_schema(),
                "z_index": {"type": "integer"},
            },
            required=["slide", "type", "x", "y", "w", "h"],
        ),
        "result_schema": _ref("shape_add_result"),
        "errors": [INVALID_SLIDE, SCHEMA_ERROR],
    },
    "table_add": {
        "kind": "mutation",
        "summary": "Insert or replace a table node in a slot on a slide.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "data": _ref("table_data"),
            },
            required=["slide", "slot", "data"],
        ),
        "result_schema": _ref("table_add_result"),
        "errors": [INVALID_SLIDE, INVALID_SLOT, SCHEMA_ERROR],
    },
    "pattern_add": {
        "kind": "mutation",
        "summary": "Insert or replace a slot-bound freeform composition pattern on a slide.",
        "input_schema": _object_schema(
            {
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "type": {"type": "string", "enum": list(PATTERN_TYPE_VALUES)},
                "columns": _integer_schema(minimum=1),
                "data": _ref("pattern_data"),
            },
            required=["slide", "type", "data"],
        ),
        "result_schema": _ref("pattern_add_result"),
        "errors": [INVALID_SLIDE, INVALID_SLOT, SCHEMA_ERROR],
    },
}

_BATCH_ERROR_CODES = sorted(
    {
        SCHEMA_ERROR,
        *(
            error
            for payload in MUTATION_CONTRACTS.values()
            for error in payload["errors"]
        ),
    }
)

COMMAND_CONTRACTS: dict[str, dict[str, Any]] = {
    "batch": {
        "kind": "cli",
        "summary": "Apply multiple mutation operations from JSON stdin in one atomic write.",
        "cli_command": _cli_command("batch"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
            },
            required=["path"],
        ),
        "stdin_schema": _array_schema(_ref("batch_operation")),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("batch_result")),
            }
        ],
        "errors": _BATCH_ERROR_CODES,
    },
    "build": {
        "kind": "cli",
        "summary": "Reflow the deck, persist computed state, and write a PPTX artifact.",
        "cli_command": _cli_command("build"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "output": _string_schema(min_length=1),
            },
            required=["path", "output"],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("build_result"))}
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR, TEMPLATE_CHANGED],
    },
    "chart.add": {
        "kind": "cli",
        "summary": "Create or replace a chart node in a slide slot.",
        "cli_command": _cli_command("chart", "add"),
        "mutation_command": "chart_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "type": {"type": "string", "enum": list(CHART_TYPE_VALUES)},
                "data": _ref("chart_data"),
                "data_file": _string_schema(min_length=1),
                "title": {"type": ["string", "null"]},
            },
            required=["path", "slide", "slot", "type"],
            one_of=[{"required": ["data"]}, {"required": ["data_file"]}],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("chart_add_result"))}
        ],
        "errors": [FILE_NOT_FOUND, *MUTATION_CONTRACTS["chart_add"]["errors"]],
    },
    "chart.update": {
        "kind": "cli",
        "summary": "Update the data payload for an existing chart node.",
        "cli_command": _cli_command("chart", "update"),
        "mutation_command": "chart_update",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "node": _string_schema(min_length=1),
                "data": _ref("chart_data"),
            },
            required=["path", "node", "data"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("chart_update_result")),
            }
        ],
        "errors": MUTATION_CONTRACTS["chart_update"]["errors"],
    },
    "table.add": {
        "kind": "cli",
        "summary": "Create or replace a table node in a slide slot.",
        "cli_command": _cli_command("table", "add"),
        "mutation_command": "table_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "data": _ref("table_data"),
                "data_file": _string_schema(min_length=1),
            },
            required=["path", "slide", "slot"],
            one_of=[{"required": ["data"]}, {"required": ["data_file"]}],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("table_add_result"))}
        ],
        "errors": [FILE_NOT_FOUND, *MUTATION_CONTRACTS["table_add"]["errors"]],
    },
    "pattern.add": {
        "kind": "cli",
        "summary": "Create or replace a slot-bound pattern node in a slide.",
        "cli_command": _cli_command("pattern", "add"),
        "mutation_command": "pattern_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "type": {"type": "string", "enum": list(PATTERN_TYPE_VALUES)},
                "columns": _integer_schema(minimum=1),
                "data": _ref("pattern_data"),
                "data_file": _string_schema(min_length=1),
            },
            required=["path", "slide", "type"],
            one_of=[{"required": ["data"]}, {"required": ["data_file"]}],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("pattern_add_result")),
            }
        ],
        "errors": [FILE_NOT_FOUND, *MUTATION_CONTRACTS["pattern_add"]["errors"]],
    },
    "contract": {
        "kind": "cli",
        "summary": "Emit the canonical machine-readable contract for commands, mutations, tools, and errors.",
        "cli_command": _cli_command("contract"),
        "input_schema": _object_schema({}),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _object_schema({}, additional_properties=True),
            }
        ],
        "errors": [],
    },
    "info": {
        "kind": "cli",
        "summary": "Dump the full deck sidecar JSON with indentation.",
        "cli_command": _cli_command("info"),
        "input_schema": _object_schema(
            {"path": _string_schema(min_length=1)}, required=["path"]
        ),
        "outputs": [{"channel": "stdout", "schema": _ref("deck")}],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
    "icon.add": {
        "kind": "cli",
        "summary": "Place a built-in vector icon on a slide at absolute coordinates.",
        "cli_command": _cli_command("icon", "add"),
        "mutation_command": "icon_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "name": _string_schema(min_length=1),
                "x": _number_schema(),
                "y": _number_schema(),
                "size": _number_schema(),
                "color": _string_schema(min_length=4),
            },
            required=["path", "slide", "name", "x", "y", "size", "color"],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("icon_add_result"))}
        ],
        "errors": MUTATION_CONTRACTS["icon_add"]["errors"],
    },
    "icon.list": {
        "kind": "cli",
        "summary": "List the built-in vector icon names available for icon nodes and icon bullets.",
        "cli_command": _cli_command("icon", "list"),
        "input_schema": _object_schema({}),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("icon_list_result"))}
        ],
        "errors": [],
    },
    "init": {
        "kind": "cli",
        "summary": "Create a new deck sidecar with either a built-in theme or a learned template.",
        "cli_command": _cli_command("init"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "theme": _string_schema(min_length=1),
                "template": _string_schema(min_length=1),
                "rules": _string_schema(min_length=1),
                "force": _boolean_schema(default=False),
            },
            required=["path"],
            all_of=[
                {
                    "not": {"required": ["theme", "template"]},
                }
            ],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(
                    _object_schema(
                        {
                            "deck_id": _string_schema(min_length=1),
                            "theme": _string_schema(min_length=1),
                            "design_rules": _string_schema(min_length=1),
                            "template": _string_schema(min_length=1),
                            "template_manifest": _string_schema(min_length=1),
                        },
                        required=["deck_id", "theme", "design_rules"],
                    )
                ),
            }
        ],
        "errors": [FILE_EXISTS, FILE_NOT_FOUND, SCHEMA_ERROR, THEME_NOT_FOUND],
    },
    "inspect": {
        "kind": "cli",
        "summary": "Summarize a learned template manifest.",
        "cli_command": _cli_command("inspect"),
        "input_schema": _object_schema(
            {"path": _string_schema(min_length=1)}, required=["path"]
        ),
        "outputs": [{"channel": "stdout", "schema": _ref("inspect_result")}],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
    "learn": {
        "kind": "cli",
        "summary": "Extract a manifest from a PPTX template.",
        "cli_command": _cli_command("learn"),
        "input_schema": _object_schema(
            {
                "template_path": _string_schema(min_length=1),
                "output": _string_schema(min_length=1),
            },
            required=["template_path"],
        ),
        "outputs": [
            {
                "channel": "stderr",
                "schema": _string_schema(min_length=1),
                "kind": "warning_text",
            },
            {"channel": "stdout", "schema": _success_envelope(_ref("learn_result"))},
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
    "preview": {
        "kind": "cli",
        "summary": "Start the live preview server for a deck.",
        "cli_command": _cli_command("preview"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "port": _integer_schema(minimum=0, default=8765),
                "no_open": _boolean_schema(default=False),
            },
            required=["path"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("server_started_result")),
            },
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("server_stopped_result")),
            },
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
    "review": {
        "kind": "cli",
        "summary": "Render a deck to slide PNGs and score it against the visual QA checklist.",
        "cli_command": _cli_command("review"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "output_dir": _string_schema(min_length=1),
                "dpi": _integer_schema(minimum=1, default=200),
                "fix": _boolean_schema(default=False),
            },
            required=["path"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(
                    _object_schema(
                        {
                            "output_dir": _string_schema(min_length=1),
                            "report_path": _string_schema(min_length=1),
                            "report_json_path": _string_schema(min_length=1),
                            "overall_grade": _string_schema(min_length=1),
                            "slides": _integer_schema(minimum=0),
                            "fixes_applied": _integer_schema(minimum=0),
                        },
                        required=[
                            "output_dir",
                            "report_path",
                            "report_json_path",
                            "overall_grade",
                            "slides",
                            "fixes_applied",
                        ],
                    ),
                ),
            }
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR, TEMPLATE_CHANGED],
    },
    "shape.add": {
        "kind": "cli",
        "summary": "Add a slide-level shape primitive with explicit geometry and styling.",
        "cli_command": _cli_command("shape", "add"),
        "mutation_command": "shape_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "type": {"type": "string", "enum": list(SHAPE_TYPE_VALUES)},
                "x": _number_schema(),
                "y": _number_schema(),
                "w": _number_schema(),
                "h": _number_schema(),
                "fill": _string_schema(min_length=1),
                "color": _string_schema(min_length=1),
                "line_color": _string_schema(min_length=1),
                "line_width": _number_schema(),
                "corner_radius": _number_schema(),
                "shadow": _boolean_schema(default=False),
                "dash": {"type": "string", "enum": list(SHAPE_DASH_VALUES)},
                "opacity": _number_schema(),
                "z_index": {"type": "integer"},
            },
            required=["path", "slide", "type", "x", "y", "w", "h"],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("shape_add_result"))}
        ],
        "errors": MUTATION_CONTRACTS["shape_add"]["errors"],
    },
    "slide.add": {
        "kind": "cli",
        "summary": "Append a slide using a named layout or auto-layout selection.",
        "cli_command": _cli_command("slide", "add"),
        "mutation_command": "slide_add",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "layout": _string_schema(min_length=1),
                "auto_layout": _boolean_schema(default=False),
                "content": _ref("structured_text"),
                "image_count": _integer_schema(minimum=0, default=0),
            },
            required=["path"],
            all_of=[
                {
                    "if": {"properties": {"auto_layout": {"const": True}}},
                    "then": {"required": ["content"]},
                    "else": {"required": ["layout"]},
                }
            ],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("slide_add_result"))}
        ],
        "errors": MUTATION_CONTRACTS["slide_add"]["errors"],
    },
    "slide.remove": {
        "kind": "cli",
        "summary": "Remove a slide by index or slide id.",
        "cli_command": _cli_command("slide", "remove"),
        "mutation_command": "slide_remove",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
            },
            required=["path", "slide"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("slide_remove_result")),
            }
        ],
        "errors": MUTATION_CONTRACTS["slide_remove"]["errors"],
    },
    "slide.set-layout": {
        "kind": "cli",
        "summary": "Change a slide layout and report any unbound nodes as a warning payload.",
        "cli_command": _cli_command("slide", "set-layout"),
        "mutation_command": "slide_set_layout",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "layout": _string_schema(min_length=1),
            },
            required=["path", "slide", "layout"],
        ),
        "outputs": [
            {
                "channel": "stderr",
                "schema": _ref("slide_set_layout_warning"),
                "kind": "warning",
            },
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("slide_set_layout_result")),
            },
        ],
        "errors": MUTATION_CONTRACTS["slide_set_layout"]["errors"],
    },
    "slot.bind": {
        "kind": "cli",
        "summary": "Bind an existing node to a named slot on its slide.",
        "cli_command": _cli_command("slot", "bind"),
        "mutation_command": "slot_bind",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "node": _string_schema(min_length=1),
                "slot": _string_schema(min_length=1),
            },
            required=["path", "node", "slot"],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("slot_bind_result"))}
        ],
        "errors": MUTATION_CONTRACTS["slot_bind"]["errors"],
    },
    "slot.clear": {
        "kind": "cli",
        "summary": "Remove all content bound to a slot on a slide.",
        "cli_command": _cli_command("slot", "clear"),
        "mutation_command": "slot_clear",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
            },
            required=["path", "slide", "slot"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("slot_clear_result")),
            }
        ],
        "errors": MUTATION_CONTRACTS["slot_clear"]["errors"],
    },
    "slot.set": {
        "kind": "cli",
        "summary": "Set text or image content for a slot on a slide.",
        "cli_command": _cli_command("slot", "set"),
        "mutation_command": "slot_set",
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "slide": _ref("slide_ref"),
                "slot": _string_schema(min_length=1),
                "text": _string_schema(),
                "image": _string_schema(min_length=1),
            },
            required=["path", "slide", "slot"],
            one_of=[{"required": ["text"]}, {"required": ["image"]}],
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("slot_set_result"))}
        ],
        "errors": MUTATION_CONTRACTS["slot_set"]["errors"],
    },
    "suggest-layout": {
        "kind": "cli",
        "summary": "Recommend built-in layouts for structured text content.",
        "cli_command": _cli_command("suggest-layout"),
        "input_schema": _object_schema(
            {
                "content": _string_schema(min_length=1),
                "limit": _integer_schema(minimum=1),
            },
            required=["content"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("suggest_layout_result")),
            }
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
    "theme.apply": {
        "kind": "cli",
        "summary": "Apply a built-in theme to an existing deck.",
        "cli_command": _cli_command("theme", "apply"),
        "input_schema": _object_schema(
            {
                "path": _string_schema(min_length=1),
                "theme": _string_schema(min_length=1),
            },
            required=["path", "theme"],
        ),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("theme_apply_result")),
            }
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR, THEME_NOT_FOUND],
    },
    "theme.list": {
        "kind": "cli",
        "summary": "List the built-in themes available to new or existing decks.",
        "cli_command": _cli_command("theme", "list"),
        "input_schema": _object_schema({}),
        "outputs": [
            {
                "channel": "stdout",
                "schema": _success_envelope(_ref("theme_list_result")),
            }
        ],
        "errors": [],
    },
    "validate": {
        "kind": "cli",
        "summary": "Validate a deck and emit structured design-rule warnings.",
        "cli_command": _cli_command("validate"),
        "input_schema": _object_schema(
            {"path": _string_schema(min_length=1)}, required=["path"]
        ),
        "outputs": [
            {"channel": "stdout", "schema": _success_envelope(_ref("validate_result"))}
        ],
        "errors": [FILE_NOT_FOUND, SCHEMA_ERROR],
    },
}

AGENT_TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    name: {
        "kind": "agent_tool",
        "summary": payload["summary"],
        "input_schema": payload["input_schema"],
        "result_schema": payload["result_schema"],
        "errors": payload["errors"],
    }
    for name, payload in MUTATION_CONTRACTS.items()
}
AGENT_TOOL_CONTRACTS["build"] = {
    "kind": "agent_tool",
    "summary": "Reflow the current deck, persist computed state, and write a PPTX artifact.",
    "input_schema": _object_schema(
        {
            "output_path": _string_schema(min_length=1),
            "output": _string_schema(min_length=1),
        },
        description="`output` is retained as a legacy alias; `output_path` is the canonical key.",
    ),
    "result_schema": _ref("tool_result_build"),
    "errors": [FILE_NOT_FOUND, INVALID_TOOL_INPUT, SCHEMA_ERROR, TEMPLATE_CHANGED],
}
AGENT_TOOL_CONTRACTS["get_deck_info"] = {
    "kind": "agent_tool",
    "summary": "Read the current deck sidecar, including slides, nodes, theme, and revision.",
    "input_schema": _object_schema({}),
    "result_schema": _ref("tool_result_get_deck_info"),
    "errors": [FILE_NOT_FOUND, INVALID_TOOL_INPUT, SCHEMA_ERROR],
}

TOOL_PROFILES: dict[str, list[str]] = {
    LEGACY_ORCHESTRATOR_PROFILE: [
        "slide_add",
        "slide_set_layout",
        "slot_set",
        "slot_clear",
        "slot_bind",
        "table_add",
        "pattern_add",
        "slide_remove",
        "build",
    ],
    PREVIEW_CHAT_PROFILE: [
        "slide_add",
        "slot_set",
        "slot_clear",
        "chart_add",
        "table_add",
        "pattern_add",
        "slide_set_layout",
        "slide_remove",
        "get_deck_info",
        "build",
    ],
}


def get_tool_definitions(*, profile: str) -> list[dict[str, Any]]:
    try:
        tool_names = TOOL_PROFILES[profile]
    except KeyError as exc:
        raise KeyError(f"Unknown tool profile {profile!r}") from exc

    definitions: list[dict[str, Any]] = []
    for name in tool_names:
        payload = AGENT_TOOL_CONTRACTS[name]
        definitions.append(
            {
                "name": name,
                "description": payload["summary"],
                "input_schema": deepcopy(payload["input_schema"]),
            }
        )
    return definitions


def build_contract() -> dict[str, Any]:
    return {
        "version": CONTRACT_VERSION,
        "$defs": deepcopy(DEFINITIONS),
        "errors": deepcopy(ERROR_CONTRACTS),
        "mutations": deepcopy(MUTATION_CONTRACTS),
        "commands": deepcopy(COMMAND_CONTRACTS),
        "agent_tools": deepcopy(AGENT_TOOL_CONTRACTS),
        "tool_profiles": deepcopy(TOOL_PROFILES),
        "error_envelope": _error_envelope(),
    }


__all__ = [
    "AGENT_TOOL_CONTRACTS",
    "COMMAND_CONTRACTS",
    "CONTRACT_VERSION",
    "LEGACY_ORCHESTRATOR_PROFILE",
    "MUTATION_COMMAND_NAMES",
    "MUTATION_CONTRACTS",
    "PREVIEW_CHAT_PROFILE",
    "TOOL_PROFILES",
    "build_contract",
    "get_tool_definitions",
]
