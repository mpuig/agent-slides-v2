from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

from agent_slides.commands.mutations import apply_mutation
from agent_slides.io.sidecar import init_deck, mutate_deck
from agent_slides.model import Deck
from agent_slides.model.layout_provider import LayoutProvider
from agent_slides.preview import PreviewServer
from tests.test_preview import FakeSlideRenderer


def test_file_watcher_detects_sidecar_mutation(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = prepare_deck(tmp_path)

        async with make_server(deck_path) as server:
            async with connect(server.url) as websocket:
                initial = await receive_update(websocket)
                updated_deck, _ = mutate_deck(str(deck_path), apply_slot_mutation("watcher"))
                payload = await receive_update(websocket)

        assert initial["type"] == "slides_updated"
        assert initial["revision"] == 2
        assert initial["slides"] == [{"index": 0, "url": "/slides/0.png?rev=2", "revision": 2}]
        assert payload["type"] == "slides_updated"
        assert payload["revision"] == updated_deck.revision
        assert payload["slides"] == [
            {"index": 0, "url": "/slides/0.png?rev=3", "revision": 3}
        ]

    asyncio.run(scenario())


def test_multiple_rapid_mutations_debounce(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = prepare_deck(tmp_path)

        async with make_server(deck_path, debounce_interval=0.05) as server:
            async with connect(server.url) as websocket:
                initial = await receive_update(websocket)
                for index in range(5):
                    mutate_deck(str(deck_path), apply_slot_mutation(f"rapid-{index}"))

                updates = await collect_updates(websocket, timeout=0.25)

        assert initial["type"] == "slides_updated"
        assert initial["revision"] == 2
        assert initial["slides"] == [{"index": 0, "url": "/slides/0.png?rev=2", "revision": 2}]
        assert 1 <= len(updates) <= 2
        assert updates[-1]["type"] == "slides_updated"
        assert updates[-1]["slides"] == [{"index": 0, "url": "/slides/0.png?rev=7", "revision": 7}]
        assert updates[-1]["revision"] >= 7

    asyncio.run(scenario())


def test_server_handles_client_disconnect_gracefully(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = prepare_deck(tmp_path)

        async with make_server(deck_path) as server:
            async with connect(server.url):
                pass

            mutate_deck(str(deck_path), apply_slot_mutation("after-disconnect"))
            await asyncio.sleep(0.12)
            assert server.is_running

    asyncio.run(scenario())


def test_multiple_simultaneous_clients_receive_update(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = prepare_deck(tmp_path)

        async with make_server(deck_path) as server:
            async with (
                connect(server.url) as client_one,
                connect(server.url) as client_two,
                connect(server.url) as client_three,
            ):
                initial_updates = await asyncio.gather(
                    receive_update(client_one),
                    receive_update(client_two),
                    receive_update(client_three),
                )
                updated_deck, _ = mutate_deck(str(deck_path), apply_slot_mutation("fanout"))
                updates = await asyncio.gather(
                    receive_update(client_one),
                    receive_update(client_two),
                    receive_update(client_three),
                )

        assert all(update["revision"] == 2 for update in initial_updates)
        assert all(
            update["slides"] == [{"index": 0, "url": "/slides/0.png?rev=2", "revision": 2}]
            for update in initial_updates
        )
        assert all(update["revision"] == updated_deck.revision for update in updates)
        assert all(
            update["slides"] == [{"index": 0, "url": "/slides/0.png?rev=3", "revision": 3}]
            for update in updates
        )

    asyncio.run(scenario())


def make_server(deck_path: Path, **kwargs: Any) -> PreviewServer:
    renderer = kwargs.pop("slide_renderer", FakeSlideRenderer(deck_path, deck_path.parent / "rendered"))
    return PreviewServer(str(deck_path), host="127.0.0.1", port=0, slide_renderer=renderer, **kwargs)


def prepare_deck(tmp_path: Path) -> Path:
    deck_path = tmp_path / "deck.json"
    init_deck(str(deck_path), theme="default", design_rules="default", force=False)
    mutate_deck(
        str(deck_path),
        lambda deck, provider: apply_mutation(deck, "slide_add", {"layout": "title"}, provider),
    )
    mutate_deck(str(deck_path), apply_slot_mutation("initial"))
    return deck_path


def apply_slot_mutation(text: str):
    def mutate(deck: Deck, provider: LayoutProvider) -> str:
        apply_mutation(
            deck,
            "slot_set",
            {
                "slide": 0,
                "slot": "title",
                "text": text,
            },
            provider,
        )
        return text

    return mutate


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
