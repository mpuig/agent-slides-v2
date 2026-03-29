from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import pytest
from click.testing import CliRunner
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
from watchdog.events import FileModifiedEvent

from agent_slides.cli import cli
from agent_slides.io import computed_sidecar_path, read_deck, write_computed_deck
from agent_slides.model import (
    ChartSpec,
    ComputedNode,
    ComputedPatternElement,
    Counters,
    Deck,
    Node,
    NodeContent,
    ShapeSpec,
    Slide,
    TableSpec,
    TextBlock,
)
from agent_slides.preview import client_html_path, read_client_html
from agent_slides.preview.server import PreviewServer
from agent_slides.preview.watcher import SidecarWatcher, load_deck_payload
from tests.image_helpers import write_png


class InlineAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_srcs: list[str] = []
        self.stylesheet_hrefs: list[str] = []
        self.inline_script_count = 0
        self.inline_style_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "script":
            src = attr_map.get("src")
            if src:
                self.script_srcs.append(src)
            else:
                self.inline_script_count += 1
        if tag == "style":
            self.inline_style_count += 1
        if (
            tag == "link"
            and attr_map.get("rel") == "stylesheet"
            and attr_map.get("href")
        ):
            self.stylesheet_hrefs.append(str(attr_map["href"]))


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
                revision=revision,
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


class FakeSlideRenderer:
    def __init__(
        self, deck_path: Path, output_dir: Path, *, available: bool = True
    ) -> None:
        self.deck_path = deck_path
        self.cache_dir = output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.is_available = available
        self.render_all_calls = 0
        self.render_indices_calls: list[list[int]] = []

    def get_cached(self, slide_id: str, revision: int) -> Path | None:
        path = self.cache_dir / f"{slide_id}-{revision}.png"
        return path if path.exists() else None

    async def render_all(self, *, progress_callback=None) -> list[Path]:
        self.render_all_calls += 1
        deck = read_deck(str(self.deck_path))
        rendered: list[Path] = []
        for index, slide in enumerate(deck.slides):
            if progress_callback is not None:
                progress_callback(index, len(deck.slides))
            rendered.append(
                self._render_slide(slide.slide_id, slide.revision or deck.revision)
            )
        return rendered

    async def render_indices(
        self, slide_indices: list[int], *, progress_callback=None
    ) -> list[Path]:
        self.render_indices_calls.append(list(slide_indices))
        deck = read_deck(str(self.deck_path))
        rendered: list[Path] = []
        for index in slide_indices:
            if progress_callback is not None:
                progress_callback(index, len(deck.slides))
            slide = deck.slides[index]
            rendered.append(
                self._render_slide(slide.slide_id, slide.revision or deck.revision)
            )
        return rendered

    def _render_slide(self, slide_id: str, revision: int) -> Path:
        return write_png(
            self.cache_dir / f"{slide_id}-{revision}.png", width=48, height=36
        )


class SilentFailureSlideRenderer(FakeSlideRenderer):
    async def render_all(self, *, progress_callback=None) -> list[Path]:
        self.render_all_calls += 1
        return []

    async def render_indices(
        self, slide_indices: list[int], *, progress_callback=None
    ) -> list[Path]:
        self.render_indices_calls.append(list(slide_indices))
        return []


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
                revision=revision,
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


def make_chart_deck(*, revision: int, chart_type: str = "bar") -> Deck:
    return Deck(
        deck_id="deck-preview-chart",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                revision=revision,
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="chart",
                        chart_spec=ChartSpec(
                            chart_type=chart_type,
                            title="Quarterly revenue",
                            categories=["Q1", "Q2", "Q3"],
                            series=[
                                {"name": "North", "values": [2.0, 4.0, 5.0]},
                                {"name": "South", "values": [1.0, 3.0, 4.0]},
                            ],
                        ),
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=96.0,
                        y=120.0,
                        width=528.0,
                        height=260.0,
                        revision=revision,
                        content_type="chart",
                        font_size_pt=18.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color="#FFFFFF",
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def make_icon_preview_deck(*, revision: int) -> Deck:
    return Deck(
        deck_id="deck-preview-icon",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                revision=revision,
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="text",
                        content=NodeContent(
                            blocks=[
                                TextBlock(
                                    type="bullet", text="On track", icon="checkmark"
                                ),
                                TextBlock(
                                    type="bullet", text="Budget risk", icon="warning"
                                ),
                            ]
                        ),
                    ),
                    Node(
                        node_id="n-2",
                        type="icon",
                        icon_name="flag",
                        x=90.0,
                        y=84.0,
                        size=20.0,
                        color="#1A73E8",
                    ),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=72.0,
                        y=120.0,
                        width=420.0,
                        height=120.0,
                        font_size_pt=18.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color=None,
                        revision=revision,
                    ),
                    "n-2": ComputedNode(
                        x=90.0,
                        y=84.0,
                        width=20.0,
                        height=20.0,
                        font_size_pt=0.0,
                        font_family="Aptos",
                        color="#1A73E8",
                        bg_color=None,
                        revision=revision,
                        content_type="icon",
                    ),
                },
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )


def make_shape_deck(*, revision: int) -> Deck:
    return Deck(
        deck_id="deck-preview-shape",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title",
                revision=revision,
                nodes=[
                    Node(
                        node_id="n-1",
                        type="shape",
                        shape_spec=ShapeSpec(
                            shape_type="rectangle",
                            fill_color="#F2F2F2",
                            line_color="#1A73E8",
                            line_width=2.0,
                            shadow=True,
                            opacity=0.8,
                        ),
                        style_overrides={
                            "x": 48.0,
                            "y": 120.0,
                            "width": 624.0,
                            "height": 240.0,
                            "z_index": -1,
                        },
                    ),
                    Node(
                        node_id="n-2",
                        slot_binding="heading",
                        type="text",
                        content="Shape preview",
                    ),
                ],
                computed={
                    "n-1": ComputedNode(
                        x=48.0,
                        y=120.0,
                        width=624.0,
                        height=240.0,
                        revision=revision,
                        content_type="shape",
                    ),
                    "n-2": ComputedNode(
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
                    ),
                },
            )
        ],
        counters=Counters(slides=1, nodes=2),
    )


def make_table_deck(*, revision: int) -> Deck:
    return Deck(
        deck_id="deck-preview-table",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                revision=revision,
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="table",
                        table_spec=TableSpec(
                            headers=["Metric", "Q1", "Q2"],
                            rows=[
                                ["Revenue", "$100K", "$150K"],
                                ["Users", "1000", "1500"],
                            ],
                        ),
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=96.0,
                        y=120.0,
                        width=528.0,
                        height=220.0,
                        revision=revision,
                        content_type="table",
                        font_size_pt=0.0,
                        font_family="Aptos",
                        color="#333333",
                        bg_color="#FFFFFF",
                    )
                },
            )
        ],
        counters=Counters(slides=1, nodes=1),
    )


def make_pattern_deck(*, revision: int) -> Deck:
    return Deck(
        deck_id="deck-preview-pattern",
        revision=revision,
        theme="default",
        design_rules="default",
        slides=[
            Slide(
                slide_id="s-1",
                layout="title_content",
                revision=revision,
                nodes=[
                    Node(
                        node_id="n-1",
                        slot_binding="body",
                        type="pattern",
                        pattern_spec={
                            "pattern_type": "kpi-row",
                            "data": [
                                {"value": "87%", "label": "Adoption"},
                                {"value": "3.2x", "label": "ROI"},
                            ],
                        },
                    )
                ],
                computed={
                    "n-1": ComputedNode(
                        x=96.0,
                        y=120.0,
                        width=528.0,
                        height=220.0,
                        revision=revision,
                        content_type="pattern",
                        font_size_pt=0.0,
                        font_family="Aptos",
                        color="#333333",
                        pattern_elements=[
                            ComputedPatternElement(
                                kind="shape",
                                shape_type="rounded_rectangle",
                                x=96.0,
                                y=120.0,
                                width=252.0,
                                height=220.0,
                                fill_color="#F2F2F2",
                                line_color="#CCCCCC",
                                line_width=1.0,
                            ),
                            ComputedPatternElement(
                                kind="text",
                                text="87%",
                                x=112.0,
                                y=136.0,
                                width=220.0,
                                height=40.0,
                                font_size_pt=28.0,
                                font_family="Aptos Display",
                                color="#1A73E8",
                                font_bold=True,
                            ),
                        ],
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


def test_sidecar_watcher_supports_watching_computed_sidecar(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    computed_path = computed_sidecar_path(deck_path)
    write_deck(deck_path, make_deck(revision=1, content="First"))
    write_computed_deck(str(deck_path), make_deck(revision=1, content="First"))

    watcher = SidecarWatcher(
        deck_path,
        lambda payload: asyncio.sleep(0),
        watched_path=computed_path,
    )

    assert watcher.matches_event(FileModifiedEvent(str(computed_path)))
    assert not watcher.matches_event(FileModifiedEvent(str(deck_path)))


def test_sidecar_watcher_detects_computed_only_changes_without_revision_bump(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        deck = make_deck(revision=1, content="First")
        write_deck(deck_path, deck)
        write_computed_deck(str(deck_path), deck)
        seen_x: list[float] = []

        async def on_revision_change(payload: dict[str, object]) -> None:
            slide = payload["slides"][0]
            computed = slide["computed"]["n-1"]
            seen_x.append(float(computed["x"]))

        watcher = SidecarWatcher(
            deck_path,
            on_revision_change,
            watched_path=computed_sidecar_path(deck_path),
            debounce_ms=50,
        )
        await watcher.start()
        try:
            deck.slides[0].computed["n-1"].x = 144.0
            write_computed_deck(str(deck_path), deck)

            await asyncio.wait_for(_wait_for(lambda: seen_x == [144.0]), timeout=1.0)
        finally:
            await watcher.stop()

    asyncio.run(scenario())


def test_preview_server_watches_computed_sidecar(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    server = PreviewServer(deck_path, port=0)

    assert server._watcher.sidecar_path == deck_path.resolve()
    assert server._watcher.watched_path == computed_sidecar_path(deck_path).resolve()


def test_load_deck_payload_hydrates_icon_paths_for_preview(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_icon_preview_deck(revision=1))

    _, payload = load_deck_payload(deck_path)
    slide = payload["slides"][0]
    text_node = next(node for node in slide["nodes"] if node["type"] == "text")
    icon_node = next(node for node in slide["nodes"] if node["type"] == "icon")

    assert text_node["content"]["blocks"][0]["icon_svg_path"]
    assert text_node["content"]["blocks"][1]["icon_svg_path"]
    assert icon_node["icon_svg_path"]


def test_preview_server_serves_http_and_pushes_websocket_updates(
    tmp_path: Path, caplog
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))
        renderer = FakeSlideRenderer(deck_path, tmp_path / "rendered")

        server = PreviewServer(
            deck_path,
            host="127.0.0.1",
            port=0,
            debounce_ms=20,
            slide_renderer=renderer,
        )
        await server.start()

        try:
            html = await asyncio.to_thread(_fetch_text, f"{server.origin}/")
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )
            slide_png = await asyncio.to_thread(
                _fetch_bytes, f"{server.origin}/slides/0.png?rev=1"
            )

            assert "<svg" in html
            assert '<img id="stage-image"' in html
            assert 'id="prev-slide"' in html
            assert 'id="next-slide"' in html
            assert 'id="slide-dots"' in html
            assert 'id="slide-count"' in html
            assert 'id="status-dot"' in html
            assert "preview_backend" in payload
            assert "wrapText" in html
            assert "preserveAspectRatio" in html
            assert payload["revision"] == 1
            assert payload["preview_backend"] == "png"
            assert payload["slide_previews"] == [
                {"index": 0, "url": "/slides/0.png?rev=1", "revision": 1}
            ]
            assert slide_png.startswith(b"\x89PNG\r\n\x1a\n")
            assert renderer.render_all_calls == 1

            async with (
                connect(f"ws://127.0.0.1:{server.port}/ws") as client_one,
                connect(f"ws://127.0.0.1:{server.port}/ws") as client_two,
            ):
                initial_one = json.loads(
                    await asyncio.wait_for(client_one.recv(), timeout=1.0)
                )
                initial_two = json.loads(
                    await asyncio.wait_for(client_two.recv(), timeout=1.0)
                )

                assert initial_one["type"] == "slides_updated"
                assert initial_two["type"] == "slides_updated"
                assert initial_one["revision"] == 1
                assert initial_two["revision"] == 1
                assert initial_one["slides"] == [
                    {"index": 0, "url": "/slides/0.png?rev=1", "revision": 1}
                ]
                assert initial_two["slides"] == [
                    {"index": 0, "url": "/slides/0.png?rev=1", "revision": 1}
                ]

                updated_deck = make_deck(revision=2, content="Updated")
                write_deck(deck_path, updated_deck)
                write_computed_deck(str(deck_path), updated_deck)

                rendering_one = json.loads(
                    await asyncio.wait_for(client_one.recv(), timeout=1.0)
                )
                rendering_two = json.loads(
                    await asyncio.wait_for(client_two.recv(), timeout=1.0)
                )
                updated_one = json.loads(
                    await asyncio.wait_for(client_one.recv(), timeout=1.0)
                )
                updated_two = json.loads(
                    await asyncio.wait_for(client_two.recv(), timeout=1.0)
                )

                assert renderer.render_indices_calls == [[0]]
                assert rendering_one == {
                    "type": "rendering",
                    "path": str(deck_path),
                    "slide_index": 1,
                    "total": 1,
                }
                assert rendering_two == {
                    "type": "rendering",
                    "path": str(deck_path),
                    "slide_index": 1,
                    "total": 1,
                }
                assert updated_one["type"] == "slides_updated"
                assert updated_two["type"] == "slides_updated"
                assert updated_one["revision"] == 2
                assert updated_two["revision"] == 2
                assert updated_one["slides"] == [
                    {"index": 0, "url": "/slides/0.png?rev=2", "revision": 2}
                ]
                assert updated_two["slides"] == [
                    {"index": 0, "url": "/slides/0.png?rev=2", "revision": 2}
                ]

        finally:
            await server.stop()

    caplog.set_level("INFO")
    asyncio.run(scenario())

    messages = [record.message for record in caplog.records]
    assert any("Preview client connected" in message for message in messages)
    assert any("Preview client disconnected" in message for message in messages)


def test_preview_server_reports_initial_render_progress_to_new_clients(
    tmp_path: Path,
) -> None:
    class BlockingSlideRenderer(FakeSlideRenderer):
        def __init__(self, deck_path: Path, output_dir: Path) -> None:
            super().__init__(deck_path, output_dir)
            self.render_started = asyncio.Event()
            self.release_render = asyncio.Event()

        async def render_all(self, *, progress_callback=None) -> list[Path]:
            self.render_all_calls += 1
            deck = read_deck(str(self.deck_path))
            rendered: list[Path] = []
            for index, slide in enumerate(deck.slides):
                if progress_callback is not None:
                    progress_callback(index, len(deck.slides))
                self.render_started.set()
                await self.release_render.wait()
                rendered.append(
                    self._render_slide(slide.slide_id, slide.revision or deck.revision)
                )
            return rendered

    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))
        renderer = BlockingSlideRenderer(deck_path, tmp_path / "rendered")
        server = PreviewServer(
            deck_path,
            host="127.0.0.1",
            port=0,
            debounce_ms=20,
            slide_renderer=renderer,
        )

        start_task = asyncio.create_task(server.start())
        await asyncio.wait_for(_wait_for(lambda: server.port != 0), timeout=1.0)
        await asyncio.wait_for(renderer.render_started.wait(), timeout=1.0)

        try:
            async with connect(f"ws://127.0.0.1:{server.port}/ws") as client:
                first_message = json.loads(
                    await asyncio.wait_for(client.recv(), timeout=1.0)
                )
                second_message = json.loads(
                    await asyncio.wait_for(client.recv(), timeout=1.0)
                )

                messages = [first_message, second_message]
                assert any(message.get("type") == "rendering" for message in messages)
                rendering = next(
                    message
                    for message in messages
                    if message.get("type") == "rendering"
                )
                assert rendering == {
                    "type": "rendering",
                    "path": str(deck_path),
                    "slide_index": 1,
                    "total": 1,
                }
        finally:
            renderer.release_render.set()
            await start_task
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_waits_for_missing_deck_and_recovers_when_file_appears(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        renderer = FakeSlideRenderer(deck_path, tmp_path / "rendered")
        server = PreviewServer(
            deck_path,
            host="127.0.0.1",
            port=0,
            debounce_ms=20,
            slide_renderer=renderer,
        )
        await server.start()

        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            assert payload["status"] == "waiting"
            assert payload["message"] == "Waiting for deck..."
            assert payload["slides"] == []
            assert payload["path"] == str(deck_path.resolve())
            assert payload["preview_backend"] == "svg"
            assert renderer.render_all_calls == 0

            async with connect(f"ws://127.0.0.1:{server.port}/ws") as client:
                initial = json.loads(await asyncio.wait_for(client.recv(), timeout=1.0))

                assert initial["event"] == "deck.updated"
                assert initial["deck"]["status"] == "waiting"
                assert initial["deck"]["message"] == "Waiting for deck..."

                arrived_deck = make_deck(revision=1, content="Deck arrived")
                write_deck(deck_path, arrived_deck)
                write_computed_deck(str(deck_path), arrived_deck)

                rendering = json.loads(
                    await asyncio.wait_for(client.recv(), timeout=1.0)
                )
                updated = json.loads(await asyncio.wait_for(client.recv(), timeout=1.0))
                hydrated = json.loads(
                    await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
                )

                assert rendering == {
                    "type": "rendering",
                    "path": str(deck_path.resolve()),
                    "slide_index": 1,
                    "total": 1,
                }
                assert updated["type"] == "slides_updated"
                assert updated["revision"] == 1
                assert updated["slides"] == [
                    {"index": 0, "url": "/slides/0.png?rev=1", "revision": 1}
                ]
                assert hydrated["revision"] == 1
                assert hydrated["preview_backend"] == "png"
                assert (
                    hydrated["slides"][0]["nodes"][0]["content"]["blocks"][0]["text"]
                    == "Deck arrived"
                )
                assert hydrated["slide_previews"] == [
                    {"index": 0, "url": "/slides/0.png?rev=1", "revision": 1}
                ]
                assert renderer.render_indices_calls == [[0]]
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_serves_image_assets(tmp_path: Path) -> None:
    async def scenario() -> None:
        image_path = write_png(tmp_path / "photo.png", width=24, height=12)
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_image_deck(image_path.name, revision=1))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )
            image_bytes = await asyncio.to_thread(
                _fetch_bytes, f"{server.origin}/api/images/photo.png"
            )

            assert payload["slides"][0]["nodes"][0]["type"] == "image"
            assert payload["slides"][0]["computed"]["n-1"]["image_fit"] == "contain"
            assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_serves_cli_normalized_absolute_image_assets(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        runner = CliRunner()
        deck_path = tmp_path / "deck.json"
        image_dir = tmp_path / "assets"
        image_dir.mkdir()
        image_path = write_png(image_dir / "photo.png", width=24, height=12)

        result = runner.invoke(cli, ["init", str(deck_path), "--theme", "default"])
        assert result.exit_code == 0

        result = runner.invoke(
            cli, ["slide", "add", str(deck_path), "--layout", "image_right"]
        )
        assert result.exit_code == 0

        result = runner.invoke(
            cli,
            [
                "slot",
                "set",
                str(deck_path),
                "--slide",
                "0",
                "--slot",
                "image",
                "--image",
                str(image_path),
            ],
        )
        assert result.exit_code == 0

        payload = json.loads(result.stdout)
        image_ref = payload["data"]["image_path"]
        assert image_ref == "assets/photo.png"

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            hydrated = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )
            image_bytes = await asyncio.to_thread(
                _fetch_bytes,
                f"{server.origin}/api/images/{quote(image_ref, safe='')}",
            )
            image_node = next(
                node
                for node in hydrated["slides"][0]["nodes"]
                if node["type"] == "image"
            )

            assert image_node["image_path"] == image_ref
            assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_rejects_image_path_traversal(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        image_path = write_png(deck_dir / "photo.png", width=24, height=12)
        secret_path = tmp_path / "secret.txt"
        secret_path.write_text("top-secret\n", encoding="utf-8")
        deck_path = deck_dir / "deck.json"
        write_deck(deck_path, make_image_deck(image_path.name, revision=1))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            encoded_requests = [
                quote("../secret.txt", safe=""),
                quote(str(secret_path), safe=""),
            ]

            for encoded_path in encoded_requests:
                with pytest.raises(urllib.error.HTTPError) as exc_info:
                    await asyncio.to_thread(
                        _fetch_bytes, f"{server.origin}/api/images/{encoded_path}"
                    )

                assert exc_info.value.code == 404
                assert "Path traversal not allowed" in exc_info.value.read().decode(
                    "utf-8"
                )
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_falls_back_to_svg_when_renderer_unavailable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))
        renderer = FakeSlideRenderer(deck_path, tmp_path / "rendered", available=False)

        server = PreviewServer(
            deck_path,
            host="127.0.0.1",
            port=0,
            debounce_ms=20,
            slide_renderer=renderer,
        )
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            assert payload["preview_backend"] == "svg"
            assert (
                payload["preview_notice"]
                == "Approximate preview (LibreOffice unavailable)"
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                await asyncio.to_thread(_fetch_bytes, f"{server.origin}/slides/0.png")
            assert exc_info.value.code == 404
        finally:
            await server.stop()

    caplog.set_level("WARNING")
    asyncio.run(scenario())

    messages = [record.message for record in caplog.records]
    assert any(
        "LibreOffice not found. Using approximate SVG preview." in message
        for message in messages
    )


def test_preview_server_falls_back_to_svg_when_renderer_silently_misses_png_cache(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))
        renderer = SilentFailureSlideRenderer(deck_path, tmp_path / "rendered")

        server = PreviewServer(
            deck_path,
            host="127.0.0.1",
            port=0,
            debounce_ms=20,
            slide_renderer=renderer,
        )
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            assert payload["preview_backend"] == "svg"
            assert (
                payload["preview_notice"]
                == "Approximate preview (LibreOffice unavailable)"
            )
            assert "slide_previews" not in payload
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                await asyncio.to_thread(_fetch_bytes, f"{server.origin}/slides/0.png")
            assert exc_info.value.code == 404
        finally:
            await server.stop()

    caplog.set_level("WARNING")
    asyncio.run(scenario())

    messages = [record.message for record in caplog.records]
    assert any("did not produce cached slide images" in message for message in messages)


def test_preview_server_rejects_chat_routes(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_deck(revision=1, content="Initial"))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            with pytest.raises(InvalidStatus) as exc_info:
                async with connect(f"ws://127.0.0.1:{server.port}/chat/ws"):
                    pass

            assert exc_info.value.response.status_code == 404

            with pytest.raises(urllib.error.HTTPError) as http_exc:
                await asyncio.to_thread(_fetch_bytes, f"{server.origin}/chat")

            assert http_exc.value.code == 404

            with pytest.raises(urllib.error.HTTPError) as http_exc:
                await asyncio.to_thread(
                    _fetch_bytes, f"{server.origin}/download/../outside.pptx"
                )

            assert http_exc.value.code == 404
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_client_html_is_packaged_and_self_contained() -> None:
    html_path = client_html_path()
    parser = InlineAssetParser()
    payload = read_client_html()
    parser.feed(payload)

    assert html_path.name == "client.html"
    assert html_path.exists()
    assert parser.script_srcs == []
    assert parser.stylesheet_hrefs == []
    assert parser.inline_script_count >= 1
    assert parser.inline_style_count >= 1


def test_client_html_contains_required_preview_surface() -> None:
    payload = read_client_html()

    assert 'viewBox="0 0 720 540"' in payload
    assert 'id="stage"' in payload
    assert 'id="stage-image"' in payload
    assert 'id="prev-slide"' in payload
    assert 'id="next-slide"' in payload
    assert 'id="slide-dots"' in payload
    assert 'id="slide-count"' in payload
    assert 'id="preview-banner"' in payload
    assert 'id="render-progress"' in payload
    assert 'id="render-progress-text"' in payload
    assert 'id="render-progress-fill"' in payload
    assert 'id="status-dot"' in payload
    assert "new WebSocket" in payload
    assert "Reconnecting in" in payload
    assert "ArrowLeft" in payload
    assert "ArrowRight" in payload
    assert '"slides_updated"' in payload
    assert '"rendering"' in payload
    assert '"Waiting for deck..."' in payload
    assert 'fetch("/api/deck")' in payload
    assert "preserveAspectRatio" in payload
    assert "Approximate preview (LibreOffice unavailable)" in payload


def test_client_html_probes_png_preview_before_showing_image() -> None:
    payload = read_client_html()

    assert "const probe = new Image();" in payload
    assert 'showSurface("svg");' in payload
    assert 'showSurface("png");' in payload
    assert (
        "setPreviewBanner(currentDeck?.preview_notice || APPROXIMATE_PREVIEW_NOTICE);"
        in payload
    )


def test_client_html_wraps_text_and_renders_structured_content() -> None:
    payload = read_client_html()

    assert "wrapText" in payload
    assert "wrapTextRuns" in payload
    assert "breakLongWord" in payload
    assert "blockRuns" in payload
    assert "splitRunsByLine" in payload
    assert "nodeLines" in payload
    assert "resolvedBlockRuns" in payload
    assert "applyConditionalRuleToRuns" in payload
    assert "split(/\\r?\\n/)" in payload
    assert 'block?.type === "bullet"' in payload
    assert '"text-decoration"' in payload
    assert "createElementNS" in payload
    assert 'createSvgElement("tspan")' in payload
    assert 'createSvgElement("rect")' in payload
    assert "currentSlideIndex" in payload
    assert "updateRenderProgress" in payload
    assert "Rendering slide" in payload


def test_client_html_contains_icon_preview_helpers() -> None:
    payload = read_client_html()

    assert "renderIconPath" in payload
    assert "renderIconNode" in payload
    assert 'node.type === "icon" || computed.content_type === "icon"' in payload
    assert '"fill-rule": "evenodd"' in payload


def test_client_html_contains_chart_preview_helpers() -> None:
    payload = read_client_html()

    assert "chartTypeLabels" in payload
    assert "summarizeChart" in payload
    assert "renderChartNode" in payload
    assert "renderBarChartPreview" in payload
    assert "renderColumnChartPreview" in payload
    assert "renderLineChartPreview" in payload
    assert "resolveChartPointColors" in payload
    assert 'node.type === "chart" || computed.content_type === "chart"' in payload
    assert "Preview approximation" in payload


def test_client_html_contains_shape_preview_helpers() -> None:
    payload = read_client_html()

    assert "renderShapeNode" in payload
    assert "sortedNodes" in payload
    assert "nodeZIndex" in payload
    assert 'node.type === "shape" || computed.content_type === "shape"' in payload
    assert 'createSvgElement("ellipse"' in payload
    assert 'createSvgElement("polygon"' in payload
    assert 'createSvgElement("line"' in payload
    assert "appendShapeShadow" in payload


def test_client_html_contains_pattern_preview_helpers() -> None:
    payload = read_client_html()

    assert "renderPatternNode" in payload
    assert "renderPatternTextElement" in payload
    assert 'node.type === "pattern" || computed.content_type === "pattern"' in payload
    assert "computed.pattern_elements" in payload


def test_preview_server_serves_shape_deck_payload(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_shape_deck(revision=5))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            shape_node = payload["slides"][0]["nodes"][0]
            assert shape_node["type"] == "shape"
            assert shape_node["shape_spec"]["shape_type"] == "rectangle"
            assert shape_node["shape_spec"]["fill_color"] == "#F2F2F2"
            assert shape_node["style_overrides"]["z_index"] == -1
            assert payload["slides"][0]["computed"]["n-1"]["content_type"] == "shape"
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_serves_pattern_deck_payload(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_pattern_deck(revision=5))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            pattern_node = payload["slides"][0]["nodes"][0]
            assert pattern_node["type"] == "pattern"
            assert pattern_node["pattern_spec"]["pattern_type"] == "kpi-row"
            assert payload["slides"][0]["computed"]["n-1"]["content_type"] == "pattern"
            assert len(payload["slides"][0]["computed"]["n-1"]["pattern_elements"]) == 2
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_client_html_contains_table_preview_helpers() -> None:
    payload = read_client_html()

    assert "renderTableNode" in payload
    assert "tableColumnAlignments" in payload
    assert "tableColumnWidths" in payload
    assert "resolveTableCellStyle" in payload
    assert 'node.type === "table" || computed.content_type === "table"' in payload


def test_load_deck_payload_includes_conditional_formatting_rules(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    write_deck(deck_path, make_deck(revision=1, content="Revenue +23% is urgent"))

    revision, payload = load_deck_payload(deck_path)

    assert revision == 1
    assert payload["conditional_formatting"]["color_aliases"]["green"] == "#1B8A2D"
    assert any(
        rule["pattern"] == "keyword"
        for rule in payload["conditional_formatting"]["text_rules"]
    )


def test_preview_server_serves_chart_deck_payload(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_chart_deck(revision=4))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            chart_node = payload["slides"][0]["nodes"][0]
            assert chart_node["type"] == "chart"
            assert chart_node["chart_spec"]["chart_type"] == "bar"
            assert chart_node["chart_spec"]["title"] == "Quarterly revenue"
            assert chart_node["chart_spec"]["categories"] == ["Q1", "Q2", "Q3"]
            assert chart_node["chart_spec"]["series"][1]["values"] == [1.0, 3.0, 4.0]
            assert payload["slides"][0]["computed"]["n-1"]["content_type"] == "chart"
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_preview_server_serves_table_deck_payload(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_table_deck(revision=5))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(
                await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck")
            )

            table_node = payload["slides"][0]["nodes"][0]
            assert table_node["type"] == "table"
            assert table_node["table_spec"]["headers"] == ["Metric", "Q1", "Q2"]
            assert table_node["table_spec"]["rows"][0] == ["Revenue", "$100K", "$150K"]
            assert payload["slides"][0]["computed"]["n-1"]["content_type"] == "table"
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


def _fetch_response(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:  # noqa: S310 - localhost test server
        return {
            "body": response.read(),
            "headers": dict(response.headers.items()),
        }
