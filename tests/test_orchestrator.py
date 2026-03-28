from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent_slides.io import init_deck, read_deck
from agent_slides.model.constraints import Constraint
from agent_slides.preview import orchestrator as orchestrator_module
from agent_slides.preview.orchestrator import DeckOrchestrator


def test_orchestrator_executes_tool_calls_and_preserves_conversation_history(
    tmp_path: Path, monkeypatch
) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), "default", "default", False)

    api_calls: list[dict[str, Any]] = []
    thread_calls: list[str] = []

    install_fake_anthropic(
        monkeypatch,
        api_calls,
        [
            fake_message(
                fake_tool_use(
                    "toolu_1",
                    "slide_add",
                    {
                        "layout": "title",
                    },
                )
            ),
            fake_message(fake_text("Added the title slide.")),
            fake_message(fake_tool_use("toolu_2", "get_deck_info", {})),
            fake_message(fake_text("The deck currently has one slide.")),
        ],
    )
    install_inline_to_thread(monkeypatch, thread_calls)

    orchestrator = DeckOrchestrator(str(deck_path), api_key="test-key")

    first_turn = asyncio.run(collect_responses(orchestrator.handle_message("Create the first slide.")))
    second_turn = asyncio.run(collect_responses(orchestrator.handle_message("What is in the deck now?")))

    assert first_turn[0].type == "thinking"
    assert first_turn[1].type == "tool_call"
    assert first_turn[1].tool_name == "slide_add"
    assert first_turn[1].tool_result["ok"] is True
    assert first_turn[1].tool_result["mutation"] == "slide_add"
    assert first_turn[1].tool_result["result"] == {
        "layout": "title",
        "slide_id": "s-1",
        "slide_index": 0,
    }
    warning_codes = {
        warning["code"] for warning in first_turn[1].tool_result["validation"]["warnings"]
    }
    assert "MISSING_CLOSING_SLIDE" in warning_codes
    assert first_turn[-1].type == "assistant_message"
    assert first_turn[-1].text == "Added the title slide."
    assert second_turn[-1].text == "The deck currently has one slide."

    deck = read_deck(str(deck_path))
    assert len(deck.slides) == 1
    assert api_calls[0]["messages"] == [{"role": "user", "content": "Create the first slide."}]
    assert {tool["name"] for tool in api_calls[0]["tools"]} == {
        "slide_add",
        "slot_set",
        "slot_clear",
        "chart_add",
        "slide_set_layout",
        "slide_remove",
        "get_deck_info",
        "build",
    }
    assert api_calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    tool_result_payload = json.loads(api_calls[1]["messages"][-1]["content"][0]["content"])
    assert tool_result_payload["result"]["slide_id"] == "s-1"
    assert len(api_calls[2]["messages"]) == 5
    assert api_calls[2]["messages"][0]["content"] == "Create the first slide."
    assert api_calls[2]["messages"][-1]["content"] == "What is in the deck now?"
    assert thread_calls.count("_create_message") == 4
    assert thread_calls.count("_execute_tool") == 2


def test_orchestrator_surfaces_validation_suggestions_after_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), "default", "default", False)

    api_calls: list[dict[str, Any]] = []
    install_fake_anthropic(
        monkeypatch,
        api_calls,
        [
            fake_message(fake_tool_use("toolu_1", "slide_add", {"layout": "title"})),
            fake_message(fake_text("Done.")),
        ],
    )

    monkeypatch.setattr(
        orchestrator_module,
        "validate_deck",
        lambda deck, rules: [
            Constraint(
                code="OVERFLOW",
                severity="error",
                message="Text overflowed.",
                slide_id="s-1",
                node_id="n-1",
            ),
            Constraint(
                code="UNBOUND_NODES",
                severity="error",
                message="Node is unbound.",
                slide_id="s-1",
                node_ids=["n-2"],
            ),
        ],
    )
    install_inline_to_thread(monkeypatch, [])

    orchestrator = DeckOrchestrator(str(deck_path), api_key="test-key")
    responses = asyncio.run(collect_responses(orchestrator.handle_message("Create a slide.")))

    assert responses[1].type == "tool_call"
    assert "shorter text or switch to a wider layout" in responses[1].text
    assert "orphaned content" in responses[1].text
    assert responses[1].tool_result["validation"]["suggestions"] == [
        "Some text is still overflowing. Try shorter text or switch to a wider layout.",
        "There is orphaned content on the slide. Rebind it to a slot or remove it.",
    ]


def test_orchestrator_retries_invalid_tool_calls_once_then_surfaces_error(
    tmp_path: Path, monkeypatch
) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), "default", "default", False)

    api_calls: list[dict[str, Any]] = []
    install_fake_anthropic(
        monkeypatch,
        api_calls,
        [
            fake_message(fake_tool_use("toolu_1", "not_a_real_tool", {})),
            fake_message(fake_tool_use("toolu_2", "still_not_real", {})),
        ],
    )
    install_inline_to_thread(monkeypatch, [])

    orchestrator = DeckOrchestrator(str(deck_path), api_key="test-key")
    responses = asyncio.run(collect_responses(orchestrator.handle_message("Do something impossible.")))

    assert responses[1].type == "tool_call"
    assert responses[1].tool_result["ok"] is False
    assert responses[-1].type == "error"
    assert "Tool call failed twice" in responses[-1].text
    assert len(api_calls) == 2
    assert api_calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_orchestrator_build_tool_writes_requested_output(tmp_path: Path, monkeypatch) -> None:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), "default", "default", False)

    api_calls: list[dict[str, Any]] = []
    install_fake_anthropic(
        monkeypatch,
        api_calls,
        [
            fake_message(
                fake_tool_use(
                    "toolu_1",
                    "build",
                    {
                        "output_path": "artifacts/demo.pptx",
                    },
                )
            ),
            fake_message(fake_text("Built the presentation.")),
        ],
    )
    install_inline_to_thread(monkeypatch, [])

    monkeypatch.setattr(
        orchestrator_module,
        "write_pptx",
        lambda deck, output_path, asset_base_dir: Path(output_path).write_bytes(b"pptx"),
    )

    orchestrator = DeckOrchestrator(str(deck_path), api_key="test-key")
    responses = asyncio.run(collect_responses(orchestrator.handle_message("Export the deck.")))

    output_path = tmp_path / "artifacts" / "demo.pptx"
    assert output_path.read_bytes() == b"pptx"
    assert responses[1].tool_result == {
        "ok": True,
        "output": str(output_path),
        "slides": 0,
    }
    assert responses[-1].text == "Built the presentation."


async def collect_responses(iterator: Any) -> list[Any]:
    responses = []
    async for item in iterator:
        responses.append(item)
    return responses


def install_inline_to_thread(monkeypatch, recorded_names: list[str]) -> None:
    async def fake_to_thread(func, /, *args, **kwargs):
        recorded_names.append(getattr(func, "__name__", func.__class__.__name__))
        return func(*args, **kwargs)

    monkeypatch.setattr(orchestrator_module.asyncio, "to_thread", fake_to_thread)


def install_fake_anthropic(monkeypatch, api_calls: list[dict[str, Any]], responses: list[Any]) -> None:
    iterator = iter(responses)

    class FakeMessagesAPI:
        def create(self, **kwargs):
            api_calls.append(kwargs)
            return next(iterator)

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.messages = FakeMessagesAPI()

    monkeypatch.setattr(orchestrator_module, "anthropic", SimpleNamespace(Anthropic=FakeClient))


def fake_message(*content_blocks: Any) -> Any:
    return SimpleNamespace(content=list(content_blocks))


def fake_tool_use(tool_id: str, name: str, payload: dict[str, Any]) -> Any:
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=payload)


def fake_text(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)
