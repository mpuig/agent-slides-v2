from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from websockets.asyncio.client import connect

from agent_slides.model import ComputedNode, Counters, Deck, Node, Slide
from agent_slides.preview.server import PreviewServer
from agent_slides.preview.watcher import SidecarWatcher
from tests.image_helpers import write_png


def make_deck(*, revision: int, content: str = "Hello preview") -> Deck:
    return Deck(
        deck_id="deck-preview",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="heading",
                        type="text",
                        content=content,
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=54.0,
                        width=576.0,
                        height=80.0,
                        font_size_pt=28.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color="#FFFFFF",
                        font_bold=True,
                        revision=revision,
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def write_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def make_image_deck(image_path: str, *, revision: int) -> Deck:
    return Deck(
        deck_id="deck-preview-image",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="image",
                        image_path=image_path,
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=60.0,
                        y=132.0,
                        width=600.0,
                        height=348.0,
                        revision=revision,
                        image_fit="contain",
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def test_sidecar_watcher_detects_revision_change_and_debounces(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="First"))
        revisions: list[int] = []

        async def on_revision_change(payload: dict[str, object]) -> None:
            revisions.append(int(payload["revision"]))

        watcher = SidecarWatcher(deck_path, on_revision_change, debounce_ms=50)
        await watcher.start()
        try:
            write_deck(deck_path, make_deck(revision=2, content="Second"))
            await asyncio.sleep(0.01)
            write_deck(deck_path, make_deck(revision=3, content="Third"))

            await asyncio.wait_for(_wait_for(lambda: revisions == [3]), timeout=1.0)
        finally:
            await watcher.stop()

    asyncio.run(scenario())


def test_preview_server_serves_http_and_pushes_websocket_updates(
    tmp_path: Path, caplog
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()

        try:
            html = await asyncio.to_thread(_fetch_text, f"{server.origin}/")
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))

            assert "<svg" in html
            assert payload["revision"] == 1

            async with (
                connect(f"ws://127.0.0.1:{server.port}/ws") as client_one,
                connect(f"ws://127.0.0.1:{server.port}/ws") as client_two,
            ):
                write_deck(deck_path, make_deck(revision=2, content="Updated"))

                updated_one = json.loads(await asyncio.wait_for(client_one.recv(), timeout=1.0))
                updated_two = json.loads(await asyncio.wait_for(client_two.recv(), timeout=1.0))

                assert updated_one["revision"] == 2
                assert updated_two["revision"] == 2
                assert updated_one["deck"]["slides"][0]["nodes"][0]["content"]["blocks"] == [
                    {"type": "paragraph", "text": "Updated", "level": 0}
                ]
                assert updated_two["deck"]["slides"][0]["nodes"][0]["content"]["blocks"] == [
                    {"type": "paragraph", "text": "Updated", "level": 0}
                ]

        finally:
            await server.stop()

    caplog.set_level("INFO")
    asyncio.run(scenario())

    messages = [record.message for record in caplog.records]
    assert any("Preview client connected" in message for message in messages)
    assert any("Preview client disconnected" in message for message in messages)


def test_preview_server_serves_image_assets(tmp_path: Path) -> None:
    async def scenario() -> None:
        image_path = write_png(tmp_path / "photo.png", width=24, height=12)
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_image_deck(image_path.name, revision=1))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))
            image_bytes = await asyncio.to_thread(_fetch_bytes, f"{server.origin}/api/images/photo.png")

            assert payload["slides"][0]["nodes"][0]["type"] == "image"
            assert payload["slides"][0]["computed"]["n-1"]["image_fit"] == "contain"
            assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        finally:
            await server.stop()

    asyncio.run(scenario())


async def _wait_for(predicate, *, interval: float = 0.01) -> None:
    while not predicate():
        await asyncio.sleep(interval)


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url) as response:  # noqa: S310 - localhost test server
        return response.read().decode("utf-8")


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:  # noqa: S310 - localhost test server
        return response.read()
