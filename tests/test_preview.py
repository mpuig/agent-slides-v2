from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from agent_slides.io import read_deck
from agent_slides.model import ChartSpec, ComputedNode, Counters, Deck, Node, Slide
from agent_slides.preview import client_html_path, read_client_html
from agent_slides.preview.server import PreviewServer
from agent_slides.preview.watcher import SidecarWatcher
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
        if tag == "link" and attr_map.get("rel") == "stylesheet" and attr_map.get("href"):
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
    def __init__(self, deck_path: Path, output_dir: Path, *, available: bool = True) -> None:
        self.deck_path = deck_path
        self.cache_dir = output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.is_available = available
        self.render_all_calls = 0
        self.render_indices_calls: list[list[int]] = []

    def get_cached(self, slide_id: str, revision: int) -> Path | None:
        path = self.cache_dir / f"{slide_id}-{revision}.png"
        return path if path.exists() else None

    async def render_all(self) -> list[Path]:
        self.render_all_calls += 1
        deck = read_deck(str(self.deck_path))
        return [self._render_slide(slide.slide_id, slide.revision or deck.revision) for slide in deck.slides]

    async def render_indices(self, slide_indices: list[int]) -> list[Path]:
        self.render_indices_calls.append(list(slide_indices))
        deck = read_deck(str(self.deck_path))
        rendered: list[Path] = []
        for index in slide_indices:
            slide = deck.slides[index]
            rendered.append(self._render_slide(slide.slide_id, slide.revision or deck.revision))
        return rendered

    def _render_slide(self, slide_id: str, revision: int) -> Path:
        return write_png(self.cache_dir / f"{slide_id}-{revision}.png", width=48, height=36)


class SilentFailureSlideRenderer(FakeSlideRenderer):
    async def render_all(self) -> list[Path]:
        self.render_all_calls += 1
        return []

    async def render_indices(self, slide_indices: list[int]) -> list[Path]:
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
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))
            slide_png = await asyncio.to_thread(_fetch_bytes, f"{server.origin}/slides/0.png?rev=1")

            assert "<svg" in html
            assert '<img id="stage-image"' in html
            assert 'id="prev-slide"' in html
            assert 'id="next-slide"' in html
            assert 'id="slide-dots"' in html
            assert 'id="slide-count"' in html
            assert 'id="status-dot"' in html
            assert 'preview_backend' in payload
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
                initial_one = json.loads(await asyncio.wait_for(client_one.recv(), timeout=1.0))
                initial_two = json.loads(await asyncio.wait_for(client_two.recv(), timeout=1.0))

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

                write_deck(deck_path, make_deck(revision=2, content="Updated"))

                updated_one = json.loads(await asyncio.wait_for(client_one.recv(), timeout=1.0))
                updated_two = json.loads(await asyncio.wait_for(client_two.recv(), timeout=1.0))

                assert renderer.render_indices_calls == [[0]]
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
                    await asyncio.to_thread(_fetch_bytes, f"{server.origin}/api/images/{encoded_path}")

                assert exc_info.value.code == 404
                assert "Path traversal not allowed" in exc_info.value.read().decode("utf-8")
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
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))

            assert payload["preview_backend"] == "svg"
            assert payload["preview_notice"] == "Approximate preview (LibreOffice unavailable)"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                await asyncio.to_thread(_fetch_bytes, f"{server.origin}/slides/0.png")
            assert exc_info.value.code == 404
        finally:
            await server.stop()

    caplog.set_level("WARNING")
    asyncio.run(scenario())

    messages = [record.message for record in caplog.records]
    assert any("LibreOffice not found. Using approximate SVG preview." in message for message in messages)


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
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))

            assert payload["preview_backend"] == "svg"
            assert payload["preview_notice"] == "Approximate preview (LibreOffice unavailable)"
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
                await asyncio.to_thread(_fetch_bytes, f"{server.origin}/download/../outside.pptx")

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
    assert 'id="status-dot"' in payload
    assert "new WebSocket" in payload
    assert "Reconnecting in" in payload
    assert "ArrowLeft" in payload
    assert "ArrowRight" in payload
    assert '"slides_updated"' in payload
    assert 'fetch("/api/deck")' in payload
    assert "preserveAspectRatio" in payload
    assert "Approximate preview (LibreOffice unavailable)" in payload


def test_client_html_probes_png_preview_before_showing_image() -> None:
    payload = read_client_html()

    assert "const probe = new Image();" in payload
    assert 'showSurface("svg");' in payload
    assert 'showSurface("png");' in payload
    assert 'setPreviewBanner(currentDeck?.preview_notice || APPROXIMATE_PREVIEW_NOTICE);' in payload


def test_client_html_wraps_text_and_renders_structured_content() -> None:
    payload = read_client_html()

    assert "wrapText" in payload
    assert "breakLongWord" in payload
    assert "nodeLines" in payload
    assert 'split(/\\r?\\n/)' in payload
    assert 'block?.type === "bullet"' in payload
    assert "createElementNS" in payload
    assert 'createSvgElement("tspan")' in payload
    assert 'createSvgElement("rect")' in payload
    assert "currentSlideIndex" in payload


def test_client_html_contains_chart_preview_helpers() -> None:
    payload = read_client_html()

    assert "chartTypeLabels" in payload
    assert "summarizeChart" in payload
    assert "renderChartNode" in payload
    assert "renderBarChartPreview" in payload
    assert "renderColumnChartPreview" in payload
    assert "renderLineChartPreview" in payload
    assert 'node.type === "chart" || computed.content_type === "chart"' in payload
    assert "Preview approximation" in payload


def test_preview_server_serves_chart_deck_payload(tmp_path: Path) -> None:
    async def scenario() -> None:
        deck_path = tmp_path / "deck.json"
        write_deck(deck_path, make_chart_deck(revision=4))

        server = PreviewServer(deck_path, host="127.0.0.1", port=0, debounce_ms=20)
        await server.start()
        try:
            payload = json.loads(await asyncio.to_thread(_fetch_text, f"{server.origin}/api/deck"))

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
