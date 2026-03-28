from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from websockets.asyncio.client import connect

from agent_slides.io.sidecar import init_deck, read_deck
from agent_slides.orchestrator import DeckConversationOrchestrator
from agent_slides.preview import PreviewServer


class FakeAnthropic:
    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        snapshot = dict(kwargs)
        snapshot["messages"] = json.loads(json.dumps(kwargs["messages"]))
        self.calls.append(snapshot)
        if not self._responses:
            raise AssertionError("No fake Anthropic responses remaining")
        return SimpleNamespace(content=self._responses.pop(0))


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def tool_use(tool_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": tool_id,
        "name": name,
        "input": payload,
    }


def prepare_deck(tmp_path: Path) -> Path:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)
    return deck_path


async def receive_update(websocket: Any, *, timeout: float = 0.5) -> dict[str, Any]:
    async with asyncio.timeout(timeout):
        message = await websocket.recv()
    return json.loads(message)


async def collect_updates(websocket: Any, *, timeout: float) -> list[dict[str, Any]]:
    updates = [await receive_update(websocket)]
    while True:
        try:
            async with asyncio.timeout(timeout):
                message = await websocket.recv()
        except TimeoutError:
            return updates
        updates.append(json.loads(message))


def test_single_message_creates_slide_and_pushes_preview_update(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = prepare_deck(tmp_path)
        client = FakeAnthropic(
            [
                [
                    tool_use("toolu-1", "slide_add", {"layout": "title"}),
                    tool_use(
                        "toolu-2",
                        "slot_set",
                        {"slide": 0, "slot": "title", "text": "Conversational Deck"},
                    ),
                ],
                [text_block("Created the opening slide.")],
            ]
        )
        orchestrator = DeckConversationOrchestrator(deck_path, client)

        async with PreviewServer(str(deck_path), host="127.0.0.1", port=0) as server:
            async with connect(server.url) as websocket:
                result = orchestrator.send_user_message("Create an opening slide")
                updates = await collect_updates(websocket, timeout=0.25)

        deck = read_deck(str(deck_path))
        assert result.ok is True
        assert result.reply == "Created the opening slide."
        assert len(deck.slides) == 1
        assert deck.slides[0].layout == "title"
        assert deck.slides[0].nodes[0].content.to_plain_text() == "Conversational Deck"
        assert len(updates) >= 1
        assert updates[-1]["deck"]["slides"][0]["nodes"][0]["content"]["blocks"] == [
            {"type": "paragraph", "text": "Conversational Deck", "level": 0}
        ]

    asyncio.run(scenario())


def test_multi_turn_conversation_preserves_history_and_builds(tmp_path: Path) -> None:
    deck_path = prepare_deck(tmp_path)
    client = FakeAnthropic(
        [
            [
                tool_use("toolu-1", "slide_add", {"layout": "title_content"}),
                tool_use("toolu-2", "slot_set", {"slide": 0, "slot": "title", "text": "Launch Plan"}),
            ],
            [text_block("Added the first slide.")],
            [
                tool_use(
                    "toolu-3",
                    "slot_set",
                    {
                        "slide": 0,
                        "slot": "body",
                        "text": "Priority one\nPriority two\nPriority three",
                    },
                ),
                tool_use("toolu-4", "slide_set_layout", {"slide": 0, "layout": "two_col"}),
                tool_use("toolu-5", "build", {"output_path": "chat-export.pptx"}),
            ],
            [text_block("Updated the deck and exported the PPTX.")],
        ]
    )
    orchestrator = DeckConversationOrchestrator(deck_path, client)

    first = orchestrator.send_user_message("Start a launch plan deck")
    second = orchestrator.send_user_message("Add the agenda, switch to two columns, and export it")

    deck = read_deck(str(deck_path))
    output_path = tmp_path / "chat-export.pptx"

    assert first.ok is True
    assert second.ok is True
    assert len(deck.slides) == 1
    assert deck.slides[0].layout == "two_col"
    assert output_path.exists()
    assert second.output_path == str(output_path)
    assert second.download_url == output_path.resolve().as_uri()
    assert len(orchestrator.messages) > len(client.calls[0]["messages"])
    assert len(client.calls[2]["messages"]) > len(client.calls[0]["messages"])


def test_auto_validate_after_mutation_surfaces_overflow_warning(tmp_path: Path) -> None:
    deck_path = prepare_deck(tmp_path)
    client = FakeAnthropic(
        [
            [
                tool_use("toolu-1", "slide_add", {"layout": "title_content"}),
                tool_use(
                    "toolu-2",
                    "slot_set",
                    {
                        "slide": 0,
                        "slot": "body",
                        "text": " ".join(["overflow"] * 1200),
                    },
                ),
            ],
            [text_block("I added the content.")],
        ]
    )
    orchestrator = DeckConversationOrchestrator(deck_path, client)

    result = orchestrator.send_user_message("Add a dense content slide")

    assert result.ok is True
    assert any(warning["code"] == "OVERFLOW" for warning in result.warnings)


def test_build_tool_creates_pptx_and_returns_download_url(tmp_path: Path) -> None:
    deck_path = prepare_deck(tmp_path)
    client = FakeAnthropic(
        [
            [
                tool_use("toolu-1", "slide_add", {"layout": "title"}),
                tool_use("toolu-2", "slot_set", {"slide": 0, "slot": "title", "text": "Export Me"}),
            ],
            [text_block("Prepared the slide.")],
            [
                tool_use("toolu-3", "build", {"output_path": "downloads/final-deck.pptx"}),
            ],
            [text_block("Export is ready.")],
        ]
    )
    orchestrator = DeckConversationOrchestrator(deck_path, client)

    orchestrator.send_user_message("Create a title slide")
    result = orchestrator.send_user_message("Build the deck")

    expected = tmp_path / "downloads" / "final-deck.pptx"
    assert result.ok is True
    assert expected.exists()
    assert result.output_path == str(expected)
    assert result.download_url == expected.resolve().as_uri()


def test_invalid_tool_call_retries_once_then_surfaces_error(tmp_path: Path) -> None:
    deck_path = prepare_deck(tmp_path)
    client = FakeAnthropic(
        [
            [
                tool_use("toolu-1", "slot_set", {"slide": 99, "slot": "title", "text": "Nope"}),
            ],
            [
                tool_use("toolu-2", "slot_set", {"slide": 99, "slot": "title", "text": "Still nope"}),
            ],
        ]
    )
    orchestrator = DeckConversationOrchestrator(deck_path, client, max_error_retries=1)

    result = orchestrator.send_user_message("Write into a missing slide")

    assert result.ok is False
    assert result.error is not None
    assert result.error["code"] == "INVALID_SLIDE"
    assert len(client.calls) == 2
    assert read_deck(str(deck_path)).slides == []
