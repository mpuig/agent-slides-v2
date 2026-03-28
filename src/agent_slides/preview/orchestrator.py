"""Anthropic-backed chat orchestrator for deck operations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised via runtime guard
    anthropic = None

from agent_slides.commands.mutations import apply_mutation
from agent_slides.contract import PREVIEW_CHAT_PROFILE, get_tool_definitions
from agent_slides.engine.reflow import reflow_deck
from agent_slides.engine.template_reflow import template_reflow
from agent_slides.engine.validator import validate_deck
from agent_slides.errors import AgentSlidesError, INVALID_TOOL_INPUT, INVALID_TOOL_NAME, OVERFLOW, UNBOUND_NODES
from agent_slides.io import mutate_deck, read_deck, resolve_manifest_path, write_computed_deck, write_pptx
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.layout_provider import TemplateLayoutRegistry, resolve_layout_provider

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_HISTORY_MESSAGES = 20
MUTATING_TOOLS = frozenset(
    {
        "slide_add",
        "slot_set",
        "slot_clear",
        "chart_add",
        "slide_set_layout",
        "slide_remove",
    }
)

SYSTEM_PROMPT = """
You are the deck editing assistant for agent-slides.

- Keep responses short and practical.
- When the user is creating a new deck, work in four phases: Phase 0 Pre-flight Questioning, Phase 1 Storyline Review, Phase 2 Build, and Phase 3 QA Review.
- In Phase 0, collect missing pre-flight inputs. For quick decks of about 5 slides, clarify or infer objective and recommendation first. For strategy decks of 8 or more slides, clarify or infer audience, objective, recommendation, scope, and target deck length.
- If the user says to just do it, infer the smallest reasonable defaults and state them briefly.
- Plan new decks with the Pyramid Principle: answer first, then supporting arguments, then evidence.
- Use a recommendation-first story: answer first, then 2-4 supporting arguments, then evidence.
- Use SCQA logic invisibly when shaping a narrative: context, complication, question, answer.
- For content slides, make the title a short sentence that states the takeaway, ensure the body proves it, and avoid bullet overload.
- Before mutating a new deck, propose a storyline with the title, the core answer, and 2-4 supporting arguments with slide coverage.
- Review the storyline section by section, check message coverage, close gaps before building, and prefer adding a missing slide over leaving an unsupported claim.
- Choose layouts isomorphically: equal pillars or themes should use `three_col`; two contrasting approaches should use `two_col` or `comparison`; structured comparisons with headers should use `comparison`; sequential narratives or one claim with proof should use `title_content`; quotes should be used deliberately.
- Avoid repeating the same content layout 3 or more slides in a row when the deck is longer than 6 slides.
- For charts, use an action-title takeaway, include an annotation or callout for the key insight, and add source lines for data claims when the user provides them.
- Prefer `slide_add` with `auto_layout: true` unless the user clearly asks for a specific layout.
- Start decks with a title slide when creating a new presentation.
- End completed decks with a closing slide when the narrative calls for a clear takeaway.
- After adding or changing content, use the tool results to check whether the content still fits.
- After meaningful edits, check the deck for action titles, evidence coverage, bullet overload, source lines for data claims, layout variety, and chart clarity.
- When the user asks to build, export, or download the deck, call `build`.
- Use deck tools instead of describing changes you did not apply.
""".strip()

TOOL_DEFINITIONS = get_tool_definitions(profile=PREVIEW_CHAT_PROFILE)


@dataclass
class ChatResponse:
    type: Literal["thinking", "tool_call", "assistant_message", "error"]
    text: str
    status: Literal["thinking", "executing", "done", "error"]
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None


class DeckOrchestrator:
    """Run multi-turn Anthropic tool-use conversations against a deck."""

    def __init__(self, deck_path: str, api_key: str):
        if anthropic is None:
            raise RuntimeError("Anthropic SDK is not installed. Install agent-slides[preview] to enable chat.")

        self.deck_path = str(Path(deck_path).resolve())
        deck = read_deck(self.deck_path)
        manifest_path = resolve_manifest_path(self.deck_path, deck)
        self._layout_provider = resolve_layout_provider(manifest_path)
        self._design_rules = load_design_rules(deck.design_rules)
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

            tool_uses = [block for block in assistant_message["content"] if block.get("type") == "tool_use"]
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
                if invalid_tool_attempts > 1:
                    error_text = self._tool_error_summary(tool_results)
                    yield ChatResponse(type="error", text=error_text, status="error")
                    return
            else:
                invalid_tool_attempts = 0

    def _create_message(self) -> Any:
        return self.client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=self._conversation_window(),
        )

    def _conversation_window(self) -> list[dict[str, Any]]:
        if len(self.conversation) <= MAX_HISTORY_MESSAGES:
            return list(self.conversation)
        return self.conversation[-MAX_HISTORY_MESSAGES:]

    def _execute_tool(self, tool_name: str, raw_input: Any) -> dict[str, Any]:
        if not isinstance(raw_input, dict):
            raise AgentSlidesError(INVALID_TOOL_INPUT, "Tool input must be an object")

        if tool_name in MUTATING_TOOLS:
            return self._run_mutation_tool(tool_name, raw_input)
        if tool_name == "get_deck_info":
            return self._run_get_deck_info()
        if tool_name == "build":
            return self._run_build_tool(raw_input)
        raise AgentSlidesError(INVALID_TOOL_NAME, f"Unsupported tool {tool_name!r}")

    def _run_mutation_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        deck, mutation_result = mutate_deck(
            self.deck_path,
            lambda deck, _provider: apply_mutation(deck, tool_name, tool_input, self._layout_provider),
        )
        validation = self._validation_payload(deck)
        return {
            "ok": True,
            "mutation": tool_name,
            "result": mutation_result,
            "validation": validation,
        }

    def _run_get_deck_info(self) -> dict[str, Any]:
        deck = read_deck(self.deck_path)
        return {
            "ok": True,
            "deck": deck.model_dump(mode="json", by_alias=True),
        }

    def _run_build_tool(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        deck = read_deck(self.deck_path)
        manifest_path = resolve_manifest_path(self.deck_path, deck)
        provider = resolve_layout_provider(manifest_path)
        if isinstance(provider, TemplateLayoutRegistry):
            template_reflow(deck, provider)
        else:
            reflow_deck(deck, provider)
        write_computed_deck(self.deck_path, deck)

        output_path = self._resolve_output_path(tool_input.get("output_path", tool_input.get("output")))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_pptx(deck, str(output_path), asset_base_dir=Path(self.deck_path).parent)
        return {
            "ok": True,
            "output": str(output_path),
            "slides": len(deck.slides),
        }

    def _resolve_output_path(self, raw_output_path: Any) -> Path:
        if raw_output_path is None:
            return Path(self.deck_path).with_suffix(".pptx")
        if not isinstance(raw_output_path, str) or not raw_output_path.strip():
            raise AgentSlidesError("INVALID_TOOL_INPUT", "Argument 'output_path' must be a non-empty string")

        candidate = Path(raw_output_path.strip()).expanduser()
        if candidate.is_absolute():
            return candidate
        return Path(self.deck_path).parent / candidate

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


__all__ = ["ChatResponse", "DeckOrchestrator", "TOOL_DEFINITIONS"]
