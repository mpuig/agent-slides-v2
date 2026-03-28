from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from agent_slides.model import ComputedNode, Counters, Deck, Node, Slide
from agent_slides.preview.renderer import SlideRenderer
from tests.image_helpers import write_png


def build_preview_deck(*, revision: int = 1) -> Deck:
    return Deck(
        deck_id="deck-preview-renderer",
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
                        content="Renderer proof",
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


def write_raw_deck(path: Path, deck: Deck) -> None:
    path.write_text(f"{deck.model_dump_json(indent=2)}\n", encoding="utf-8")


def test_slide_renderer_renders_and_reuses_cached_png(
    tmp_path: Path, monkeypatch
) -> None:
    deck_path = tmp_path / "deck.json"
    write_raw_deck(deck_path, build_preview_deck(revision=4))
    renderer = SlideRenderer(
        deck_path,
        soffice_path="soffice",
        pdftoppm_path="pdftoppm",
    )

    calls: list[list[str]] = []

    def fake_write_pptx(deck: Deck, output_path: str, *, asset_base_dir: Path | None = None) -> None:
        Path(output_path).write_bytes(b"pptx")

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "soffice":
            output_dir = Path(command[command.index("--outdir") + 1])
            source = Path(command[-1])
            output_dir.joinpath(f"{source.stem}.pdf").write_bytes(b"pdf")
            return subprocess.CompletedProcess(command, 0, stdout="pdf", stderr="")

        output_prefix = Path(command[-1])
        page_number = command[command.index("-f") + 1]
        write_png(output_prefix.with_name(f"{output_prefix.name}-{page_number}.png"), width=32, height=24)
        return subprocess.CompletedProcess(command, 0, stdout="png", stderr="")

    monkeypatch.setattr("agent_slides.preview.renderer.write_pptx", fake_write_pptx)
    monkeypatch.setattr("agent_slides.preview.renderer.subprocess.run", fake_run)

    first = asyncio.run(renderer.render_all())
    second = asyncio.run(renderer.render_all())
    cached = renderer.get_cached("s-1", 4)
    single = asyncio.run(renderer.render_slide(0))

    assert len(first) == 1
    assert first[0].is_file()
    assert second == first
    assert cached == first[0]
    assert single == first[0]
    assert [command[0] for command in calls] == ["soffice", "pdftoppm"]
