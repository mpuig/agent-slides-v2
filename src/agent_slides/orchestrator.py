"""Unified conversational orchestrators for library and chat entrypoints."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Literal

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised via runtime guard
    anthropic = None

from agent_slides.commands.mutations import apply_mutation
from agent_slides.engine.reflow import reflow_deck
from agent_slides.engine.template_reflow import template_reflow
from agent_slides.engine.validator import validate_deck
from agent_slides.errors import AgentSlidesError, OVERFLOW, SCHEMA_ERROR, UNBOUND_NODES
from agent_slides.io import mutate_deck, read_deck, resolve_manifest_path, write_computed_deck, write_pptx
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.layout_provider import TemplateLayoutRegistry, resolve_layout_provider

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MAX_ERROR_RETRIES = 1
MAX_MODEL_ROUNDS = 8
MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT = """
You are the deck editing assistant for agent-slides.

- Keep responses short and practical.
- When the user is creating a new deck, work in three phases: Plan, Build, QA.
- In Plan, collect missing pre-flight inputs: audience, objective, recommendation, scope, and desired length.
- Plan new decks with the Pyramid Principle: answer first, then supporting arguments, then evidence.
- Follow the storytelling guidance in `references/storytelling.md`.
- Follow the layout guidance in `references/layout-selection.md`.
- Use `references/chart-guide.md` when planning chart evidence, and use `references/common-mistakes.md` as a manual QA backstop.
- Use a recommendation-first story: answer first, then 2-4 supporting arguments, then evidence.
- Use SCQA logic invisibly when shaping a narrative: context, complication, question, answer.
- For content slides, make the title a short sentence that states the takeaway, and ensure the body proves it.
- When creating a new deck from a vague request, run a short pre-flight: for quick decks clarify or infer objective and recommendation first; for strategy decks clarify or infer audience, objective, recommendation, scope, and target deck length.
- If the user says to just do it, infer the smallest reasonable defaults and state them briefly.
- Before mutating a new deck, propose a storyline with the title, the core answer, and 2-4 supporting arguments with slide coverage.
- Review the storyline section by section, close message gaps before building, and prefer adding a missing slide over leaving an unsupported claim.
- Choose layouts isomorphically: equal peers should look equal, comparisons should be side by side, single narratives should read linearly, and quotes should be used deliberately.
- Avoid repeating the same content layout 3 or more slides in a row when the deck is longer than 6 slides.
- For charts, use an action-title takeaway and include an annotation or callout for the key insight.
- Prefer `slide_add` with `auto_layout: true` unless the user clearly asks for a specific layout.
- Start decks with a title slide when creating a new presentation.
- End completed decks with a closing slide when the narrative calls for a clear takeaway.
- After adding or changing content, use the tool results to check whether the content still fits.
- After meaningful edits, check the deck for action titles, evidence coverage, bullet overload, source lines for data claims, layout variety, and chart clarity.
- When the user asks to build, export, or download the deck, call `build`.
- Use deck tools instead of describing changes you did not apply.
""".strip()

SLIDE_REF_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {"type": "integer", "minimum": 0},
        {"type": "string", "minLength": 1},
    ]
}

TEXT_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["paragraph", "bullet", "heading"]},
        "text": {"type": "string"},
        "level": {"type": "integer", "minimum": 0},
    },
    "required": ["type", "text"],
    "additionalProperties": False,
}

STRUCTURED_TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": TEXT_BLOCK_SCHEMA,
        }
    },
    "required": ["blocks"],
    "additionalProperties": False,
}

CHART_DATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {"type": "string"},
        },
        "series": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["x", "y"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        "style": {
            "type": "object",
            "properties": {
                "has_legend": {"type": "boolean"},
                "has_data_labels": {"type": "boolean"},
                "series_colors": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": True,
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "slide_add",
        "description": "Add a slide. Prefer auto_layout for new content unless the user requires a specific layout.",
        "input_schema": {
            "type": "object",
            "properties": {
                "layout": {"type": "string", "minLength": 1},
                "auto_layout": {"type": "boolean"},
                "content": STRUCTURED_TEXT_SCHEMA,
                "image_count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "slot_set",
        "description": "Set text, structured content, or an image in a specific slot on a slide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slide": SLIDE_REF_SCHEMA,
                "slot": {"type": "string", "minLength": 1},
                "text": {"type": "string"},
                "content": STRUCTURED_TEXT_SCHEMA,
                "image": {"type": "string", "minLength": 1},
                "image_fit": {"type": "string", "enum": ["contain", "cover", "stretch"]},
                "font_size": {"type": "number"},
            },
            "required": ["slide", "slot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "slot_clear",
        "description": "Remove content from a slot on a slide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slide": SLIDE_REF_SCHEMA,
                "slot": {"type": "string", "minLength": 1},
            },
            "required": ["slide", "slot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "slot_bind",
        "description": "Bind an existing node to a slot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node": {"type": "string", "minLength": 1},
                "slot": {"type": "string", "minLength": 1},
            },
            "required": ["node", "slot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "chart_add",
        "description": "Insert or replace a chart in a slot on a slide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slide": SLIDE_REF_SCHEMA,
                "slot": {"type": "string", "minLength": 1},
                "type": {
                    "type": "string",
                    "enum": ["bar", "column", "line", "pie", "scatter", "area", "doughnut"],
                },
                "title": {"type": ["string", "null"]},
                "data": CHART_DATA_SCHEMA,
            },
            "required": ["slide", "slot", "type", "data"],
            "additionalProperties": False,
        },
    },
    {
        "name": "chart_update",
        "description": "Update a chart node by node id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node": {"type": "string", "minLength": 1},
                "type": {
                    "type": "string",
                    "enum": ["bar", "column", "line", "pie", "scatter", "area", "doughnut"],
                },
                "title": {"type": ["string", "null"]},
                "data": CHART_DATA_SCHEMA,
            },
            "required": ["node"],
            "additionalProperties": False,
        },
    },
    {
        "name": "slide_set_layout",
        "description": "Change the layout used by an existing slide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slide": SLIDE_REF_SCHEMA,
                "layout": {"type": "string", "minLength": 1},
            },
            "required": ["slide", "layout"],
            "additionalProperties": False,
        },
    },
    {
        "name": "slide_remove",
        "description": "Remove a slide by index or slide id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slide": SLIDE_REF_SCHEMA,
            },
            "required": ["slide"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_deck_info",
        "description": "Read the current deck state, including slides, nodes, theme, and revision.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "build",
        "description": "Reflow the deck, persist computed data, and write a PPTX artifact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
    },
]

MUTATING_TOOLS = frozenset(
    {
        "slide_add",
        "slot_set",
        "slot_clear",
        "slot_bind",
        "chart_add",
        "chart_update",
        "slide_set_layout",
        "slide_remove",
    }
)
_MISSING = object()


def _field(obj: object, name: str, default: object = _MISSING) -> Any:
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
    elif hasattr(obj, name):
        return getattr(obj, name)

    if default is not _MISSING:
        return default
    raise AttributeError(name)


def _normalize_content_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for block in blocks:
        payload: dict[str, Any]
        if isinstance(block, dict):
            payload = dict(block)
        else:
            payload = {}
            for name in ("type", "text", "id", "name", "input", "tool_use_id", "content", "is_error"):
                value = _field(block, name, _MISSING)
                if value is not _MISSING:
                    payload[name] = value
        normalized.append(payload)
    return normalized


def _text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    values = [
        str(block["text"]).strip()
        for block in blocks
        if block.get("type") == "text" and isinstance(block.get("text"), str) and block["text"].strip()
    ]
    return "\n".join(values)


def _tool_uses_from_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("type") == "tool_use"]


def _tool_result_block(tool_use_id: str, payload: dict[str, Any], *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": is_error,
        "content": json.dumps(payload, sort_keys=True),
    }


def _conversation_window(messages: list[dict[str, Any]], max_history_messages: int) -> list[dict[str, Any]]:
    if len(messages) <= max_history_messages:
        return list(messages)
    return messages[-max_history_messages:]


@dataclass(slots=True)
class OrchestratorConfig:
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_error_retries: int = DEFAULT_MAX_ERROR_RETRIES
    max_history_messages: int = MAX_HISTORY_MESSAGES
    system_prompt: str = SYSTEM_PROMPT
    output_dir: Path | None = None


@dataclass(slots=True)
class ChatResponse:
    type: Literal["thinking", "tool_call", "assistant_message", "error"]
    text: str
    status: Literal["thinking", "executing", "done", "error"]
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None


@dataclass(slots=True)
class ConversationTurnResult:
    """Structured result for one user turn."""

    ok: bool
    reply: str
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    deck_revision: int | None = None
    output_path: str | None = None
    download_url: str | None = None
    error: dict[str, Any] | None = None


class _DeckToolRuntime:
    def __init__(
        self,
        deck_path: str | Path,
        *,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self.deck_path = Path(deck_path).resolve()
        self.config = config or OrchestratorConfig()
        self.output_dir = self.config.output_dir.resolve() if self.config.output_dir is not None else self.deck_path.parent

        deck = read_deck(str(self.deck_path))
        manifest_path = resolve_manifest_path(str(self.deck_path), deck)
        self._layout_provider = resolve_layout_provider(manifest_path)
        self._design_rules = load_design_rules(deck.design_rules)

    def _execute_tool(self, tool_name: str, raw_input: Any) -> dict[str, Any]:
        if not isinstance(raw_input, dict):
            raise AgentSlidesError(SCHEMA_ERROR, "Tool input must be an object")

        if tool_name in MUTATING_TOOLS:
            return self._run_mutation_tool(tool_name, raw_input)
        if tool_name == "get_deck_info":
            return self._run_get_deck_info()
        if tool_name == "build":
            return self._run_build_tool(raw_input)
        raise AgentSlidesError("INVALID_TOOL_NAME", f"Unsupported tool {tool_name!r}")

    def _run_mutation_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        deck, mutation_result = mutate_deck(
            str(self.deck_path),
            lambda deck, _provider: apply_mutation(deck, tool_name, tool_input, self._layout_provider),
        )
        validation = self._validation_payload(deck)
        return {
            "ok": True,
            "tool": tool_name,
            "mutation": tool_name,
            "result": mutation_result,
            "validation": validation,
            "warnings": validation["warnings"],
            "deck_revision": deck.revision,
        }

    def _run_get_deck_info(self) -> dict[str, Any]:
        deck = read_deck(str(self.deck_path))
        return {
            "ok": True,
            "tool": "get_deck_info",
            "deck": deck.model_dump(mode="json", by_alias=True),
            "deck_revision": deck.revision,
        }

    def _run_build_tool(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        deck = read_deck(str(self.deck_path))
        manifest_path = resolve_manifest_path(str(self.deck_path), deck)
        if manifest_path is not None:
            deck.template_manifest = manifest_path
        provider = resolve_layout_provider(manifest_path)
        if isinstance(provider, TemplateLayoutRegistry):
            template_reflow(deck, provider)
        else:
            reflow_deck(deck, provider)
        write_computed_deck(str(self.deck_path), deck)

        output_path = self._resolve_output_path(tool_input)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_pptx(deck, str(output_path), asset_base_dir=self.deck_path.parent)
        validation = self._validation_payload(deck)
        return {
            "ok": True,
            "tool": "build",
            "result": {
                "slides": len(deck.slides),
                "output": str(output_path),
                "output_path": str(output_path),
            },
            "slides": len(deck.slides),
            "output": str(output_path),
            "output_path": str(output_path),
            "download_url": output_path.resolve().as_uri(),
            "validation": validation,
            "warnings": validation["warnings"],
            "deck_revision": deck.revision,
        }

    def _resolve_output_path(self, tool_input: dict[str, Any]) -> Path:
        raw_output_path = tool_input.get("output_path")
        legacy_output = tool_input.get("output")
        if raw_output_path is None and legacy_output is not None:
            raw_output_path = legacy_output

        if raw_output_path is None:
            return self.output_dir / f"{self.deck_path.stem}.pptx"
        if not isinstance(raw_output_path, str) or not raw_output_path.strip():
            raise AgentSlidesError(SCHEMA_ERROR, "Argument 'output_path' must be a non-empty string")

        candidate = Path(raw_output_path.strip()).expanduser()
        if candidate.is_absolute():
            return candidate
        return self.output_dir / candidate

    def _validation_payload(self, deck: Any) -> dict[str, Any]:
        warnings = validate_deck(deck, self._design_rules)
        suggestions = [suggestion for constraint in warnings if (suggestion := self._constraint_suggestion(constraint))]
        return {
            "clean": not warnings,
            "warnings": [warning.model_dump(mode="json") for warning in warnings],
            "suggestions": suggestions,
        }

    def _constraint_suggestion(self, constraint: Constraint) -> str | None:
        if constraint.code == OVERFLOW:
            return "Some text is still overflowing. Try shorter text or switch to a wider layout."
        if constraint.code == UNBOUND_NODES:
            return "There is orphaned content on the slide. Rebind it to a slot or remove it."
        return None

    def _tool_response_text(self, tool_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok", True):
            return f"{tool_name} failed: {result['error']['message']}"

        validation = result.get("validation")
        suggestions = validation.get("suggestions", []) if isinstance(validation, dict) else []
        if suggestions:
            return f"{tool_name} completed. " + " ".join(suggestions)
        return f"{tool_name} completed."

    def _tool_error_summary(self, tool_results: list[dict[str, Any]]) -> str:
        for block in reversed(tool_results):
            try:
                payload = json.loads(str(block.get("content", "{}")))
            except json.JSONDecodeError:
                continue
            if not payload.get("ok", True):
                error = payload.get("error", {})
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return f"Tool call failed twice: {message}"
        return "Tool call failed twice and could not be recovered."

    def _error_payload(self, tool_name: str, exc: Exception) -> dict[str, Any]:
        if isinstance(exc, AgentSlidesError):
            message = exc.message
            code = exc.code
            details = exc.details
        else:
            message = str(exc) or exc.__class__.__name__
            code = exc.__class__.__name__
            details = {}
        return {
            "ok": False,
            "tool": tool_name,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
        }

    def _deck_revision(self) -> int | None:
        try:
            return read_deck(str(self.deck_path)).revision
        except AgentSlidesError:
            return None


class DeckConversationOrchestrator(_DeckToolRuntime):
    """Run Anthropic-style tool-use conversations against a deck sidecar."""

    def __init__(
        self,
        deck_path: str | Path,
        anthropic_client: Any,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        output_dir: str | Path | None = None,
        max_error_retries: int = DEFAULT_MAX_ERROR_RETRIES,
        config: OrchestratorConfig | None = None,
    ) -> None:
        resolved_config = config or OrchestratorConfig(
            model=model,
            max_tokens=max_tokens,
            max_error_retries=max_error_retries,
            output_dir=Path(output_dir).resolve() if output_dir is not None else None,
        )
        super().__init__(deck_path, config=resolved_config)
        self.anthropic_client = anthropic_client
        self.messages: list[dict[str, Any]] = []

    def send_user_message(self, prompt: str) -> ConversationTurnResult:
        """Append a user prompt and execute tool rounds until the assistant responds."""

        self.messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
        reply = ""
        tool_results: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        output_path: str | None = None
        download_url: str | None = None
        last_error: dict[str, Any] | None = None
        error_retries = 0

        for _ in range(MAX_MODEL_ROUNDS):
            response = self.anthropic_client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=self.config.system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=_conversation_window(self.messages, self.config.max_history_messages),
            )
            assistant_blocks = _normalize_content_blocks(_field(response, "content"))
            self.messages.append({"role": "assistant", "content": assistant_blocks})

            current_reply = _text_from_blocks(assistant_blocks)
            if current_reply:
                reply = current_reply

            tool_uses = _tool_uses_from_blocks(assistant_blocks)
            if not tool_uses:
                return ConversationTurnResult(
                    ok=last_error is None,
                    reply=reply,
                    tool_results=tool_results,
                    warnings=warnings,
                    deck_revision=self._deck_revision(),
                    output_path=output_path,
                    download_url=download_url,
                    error=last_error,
                )

            result_blocks: list[dict[str, Any]] = []
            had_error = False
            turn_succeeded = False

            for tool_use in tool_uses:
                tool_name = str(tool_use.get("name", "")).strip()
                try:
                    payload = self._execute_tool(tool_name, tool_use.get("input", {}))
                    is_error = not payload.get("ok", True)
                except Exception as exc:  # pragma: no cover - defensive
                    payload = self._error_payload(tool_name, exc)
                    is_error = True

                tool_results.append(payload)
                result_blocks.append(_tool_result_block(str(tool_use["id"]), payload, is_error=is_error))

                if is_error:
                    had_error = True
                    last_error = payload["error"]
                    continue

                turn_succeeded = True
                last_error = None
                warnings = payload.get("warnings", warnings)
                output_path = payload.get("output_path", output_path)
                download_url = payload.get("download_url", download_url)

            self.messages.append({"role": "user", "content": result_blocks})

            if had_error:
                if error_retries >= self.config.max_error_retries:
                    return ConversationTurnResult(
                        ok=False,
                        reply=reply,
                        tool_results=tool_results,
                        warnings=warnings,
                        deck_revision=self._deck_revision(),
                        output_path=output_path,
                        download_url=download_url,
                        error=last_error,
                    )
                error_retries += 1
            elif turn_succeeded:
                error_retries = 0

        raise RuntimeError("Conversation exceeded the maximum tool-use rounds")


class DeckOrchestrator(_DeckToolRuntime):
    """Run multi-turn Anthropic tool-use conversations against a deck."""

    def __init__(
        self,
        deck_path: str | Path,
        api_key: str,
        *,
        config: OrchestratorConfig | None = None,
    ) -> None:
        if anthropic is None:
            raise RuntimeError("Anthropic SDK is not installed. Install agent-slides[preview] to enable chat.")

        super().__init__(deck_path, config=config)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.conversation: list[dict[str, Any]] = []

    async def handle_message(self, user_text: str) -> AsyncIterator[ChatResponse]:
        """Process one user turn and yield status updates as work completes."""

        self.conversation.append({"role": "user", "content": user_text})
        yield ChatResponse(type="thinking", text="Thinking about the deck update.", status="thinking")

        invalid_tool_attempts = 0
        api_attempts = 0

        while True:
            try:
                message = await asyncio.to_thread(self._create_message)
            except Exception as exc:
                if api_attempts == 0:
                    api_attempts += 1
                    yield ChatResponse(
                        type="thinking",
                        text="Anthropic request failed once; retrying.",
                        status="thinking",
                    )
                    continue
                yield ChatResponse(type="error", text=f"Anthropic API error: {exc}", status="error")
                return

            api_attempts = 0
            assistant_message = self._message_to_conversation_item(message)
            self.conversation.append(assistant_message)

            tool_uses = _tool_uses_from_blocks(assistant_message["content"])
            if not tool_uses:
                text = self._extract_text(assistant_message["content"]) or "Done."
                yield ChatResponse(type="assistant_message", text=text, status="done")
                return

            tool_results: list[dict[str, Any]] = []
            saw_tool_error = False
            for block in tool_uses:
                tool_name = str(block.get("name", "")).strip()
                try:
                    result = await asyncio.to_thread(self._execute_tool, tool_name, block.get("input"))
                    saw_tool_error = saw_tool_error or not result.get("ok", True)
                    response_text = self._tool_response_text(tool_name, result)
                except Exception as exc:  # pragma: no cover - defensive
                    saw_tool_error = True
                    result = self._error_payload(tool_name, exc)
                    response_text = self._tool_response_text(tool_name, result)

                yield ChatResponse(
                    type="tool_call",
                    text=response_text,
                    status="executing",
                    tool_name=tool_name or None,
                    tool_result=result,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.get("id"),
                        "content": json.dumps(result, sort_keys=True),
                        "is_error": not result.get("ok", True),
                    }
                )

            self.conversation.append({"role": "user", "content": tool_results})

            if saw_tool_error:
                invalid_tool_attempts += 1
                if invalid_tool_attempts > self.config.max_error_retries:
                    error_text = self._tool_error_summary(tool_results)
                    yield ChatResponse(type="error", text=error_text, status="error")
                    return
            else:
                invalid_tool_attempts = 0

    def _create_message(self) -> Any:
        return self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self.config.system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=_conversation_window(self.conversation, self.config.max_history_messages),
        )

    def _message_to_conversation_item(self, message: Any) -> dict[str, Any]:
        content = [self._serialize_content_block(block) for block in getattr(message, "content", [])]
        return {
            "role": "assistant",
            "content": content,
        }

    def _serialize_content_block(self, block: Any) -> dict[str, Any]:
        if isinstance(block, dict):
            return dict(block)
        if hasattr(block, "model_dump"):
            return dict(block.model_dump(mode="json"))

        block_type = getattr(block, "type", None)
        payload: dict[str, Any] = {}
        if block_type is not None:
            payload["type"] = block_type
        for key in ("id", "name", "input", "text"):
            value = getattr(block, key, None)
            if value is not None:
                payload[key] = value
        if payload:
            return payload
        return {"type": "unknown", "text": str(block)}

    def _extract_text(self, content: list[dict[str, Any]]) -> str:
        texts = [str(block.get("text", "")).strip() for block in content if block.get("type") == "text"]
        return "\n".join(text for text in texts if text).strip()


__all__ = [
    "ChatResponse",
    "ConversationTurnResult",
    "DeckConversationOrchestrator",
    "DeckOrchestrator",
    "DEFAULT_MODEL",
    "OrchestratorConfig",
    "SYSTEM_PROMPT",
    "TOOL_DEFINITIONS",
]
