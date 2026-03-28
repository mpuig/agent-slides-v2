"""Conversational orchestration on top of the deck mutation pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_slides.commands.mutations import SUPPORTED_MUTATION_COMMANDS, apply_mutation
from agent_slides.contract import LEGACY_ORCHESTRATOR_PROFILE, get_tool_definitions
from agent_slides.engine.reflow import reflow_deck
from agent_slides.engine.template_reflow import template_reflow
from agent_slides.engine.validator import validate_deck
from agent_slides.errors import AgentSlidesError, INVALID_TOOL_INPUT, INVALID_TOOL_NAME, SCHEMA_ERROR
from agent_slides.io import mutate_deck, read_deck, resolve_manifest_path, write_computed_deck, write_pptx
from agent_slides.model.design_rules import load_design_rules
from agent_slides.model.layout_provider import TemplateLayoutRegistry, resolve_layout_provider

DEFAULT_MODEL = "claude-3-7-sonnet-latest"
DEFAULT_MAX_TOKENS = 1024
MAX_MODEL_ROUNDS = 8

TOOL_SCHEMAS = get_tool_definitions(profile=LEGACY_ORCHESTRATOR_PROFILE)

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


def _serialize_error(exc: AgentSlidesError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        **exc.details,
    }


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


class DeckConversationOrchestrator:
    """Run Anthropic-style tool-use conversations against a deck sidecar."""

    def __init__(
        self,
        deck_path: str | Path,
        anthropic_client: Any,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        output_dir: str | Path | None = None,
        max_error_retries: int = 1,
    ) -> None:
        self.deck_path = Path(deck_path).resolve()
        self.anthropic_client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens
        self.output_dir = Path(output_dir).resolve() if output_dir is not None else self.deck_path.parent
        self.max_error_retries = max_error_retries
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
                model=self.model,
                max_tokens=self.max_tokens,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
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
                payload, is_error = self._execute_tool_use(tool_use)
                tool_results.append(payload)
                result_blocks.append(
                    _tool_result_block(str(tool_use["id"]), payload, is_error=is_error)
                )
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
                if error_retries >= self.max_error_retries:
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

    def _execute_tool_use(self, tool_use: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        name = tool_use.get("name")
        raw_input = tool_use.get("input", {})
        if not isinstance(raw_input, dict):
            error = AgentSlidesError(INVALID_TOOL_INPUT, f"Tool {name!r} requires an object input payload")
            return {"ok": False, "tool": name, "error": _serialize_error(error)}, True

        try:
            if name == "build":
                return self._execute_build(raw_input), False

            if name not in SUPPORTED_MUTATION_COMMANDS:
                raise AgentSlidesError(
                    INVALID_TOOL_NAME,
                    f"Unsupported tool {name!r}. Supported tools: {', '.join(sorted((*SUPPORTED_MUTATION_COMMANDS, 'build')))}",
                )

            deck, result = mutate_deck(
                str(self.deck_path),
                lambda deck, provider: apply_mutation(deck, str(name), raw_input, provider),
            )
            warnings = self._warnings_for_deck(deck)
            return {
                "ok": True,
                "tool": name,
                "result": result,
                "warnings": warnings,
                "deck_revision": deck.revision,
            }, False
        except AgentSlidesError as exc:
            return {"ok": False, "tool": name, "error": _serialize_error(exc)}, True

    def _execute_build(self, args: dict[str, Any]) -> dict[str, Any]:
        output_value = args.get("output_path", args.get("output"))
        if output_value is None:
            output_path = self.output_dir / f"{self.deck_path.stem}.pptx"
        elif isinstance(output_value, str) and output_value.strip():
            candidate = Path(output_value.strip())
            output_path = candidate if candidate.is_absolute() else self.output_dir / candidate
        else:
            raise AgentSlidesError(SCHEMA_ERROR, "Build tool argument 'output_path' must be a non-empty string")

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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_pptx(deck, str(output_path), asset_base_dir=self.deck_path.parent)
        return {
            "ok": True,
            "tool": "build",
            "result": {
                "slides": len(deck.slides),
                "output": str(output_path),
            },
            "warnings": self._warnings_for_deck(deck),
            "deck_revision": deck.revision,
            "output_path": str(output_path),
            "download_url": output_path.resolve().as_uri(),
        }

    def _deck_revision(self) -> int | None:
        try:
            return read_deck(str(self.deck_path)).revision
        except AgentSlidesError:
            return None

    def _warnings_for_deck(self, deck: Any) -> list[dict[str, Any]]:
        rules = load_design_rules(deck.design_rules)
        return [warning.model_dump(mode="json") for warning in validate_deck(deck, rules)]
