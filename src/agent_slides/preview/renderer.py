"""LibreOffice-backed slide renderer for preview PNG generation."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent_slides.io import read_deck, resolve_manifest_path, write_pptx
from agent_slides.model import Deck, Slide


class SlideRenderError(RuntimeError):
    """Raised when a slide preview render fails."""


class SlideRenderer:
    """Render deck slides to PNG files and cache them by slide revision."""

    def __init__(
        self,
        deck_path: str | Path,
        *,
        soffice_path: str | None = None,
        pdftoppm_path: str | None = None,
        resolution: int = 200,
    ) -> None:
        self.deck_path = Path(deck_path).resolve()
        self.cache_dir = Path(tempfile.mkdtemp(prefix="agent-slides-preview-"))
        self._rendered: dict[str, Path] = {}
        self._lock = asyncio.Lock()
        self._resolution = resolution
        self.soffice_path = soffice_path or shutil.which("soffice")
        self.pdftoppm_path = pdftoppm_path or shutil.which("pdftoppm")

    @property
    def is_available(self) -> bool:
        return bool(self.soffice_path and self.pdftoppm_path)

    def get_cached(self, slide_id: str, revision: int) -> Path | None:
        cached = self._rendered.get(self._cache_key(slide_id, revision))
        if cached is None or not cached.is_file():
            return None
        return cached

    async def render_slide(self, slide_index: int) -> Path:
        deck = self._load_deck()
        slide = deck.slides[slide_index]
        slide_revision = self._slide_revision(slide, deck.revision)
        cached = self.get_cached(slide.slide_id, slide_revision)
        if cached is not None:
            return cached

        await self._render_indices(deck, [slide_index])
        rendered = self.get_cached(slide.slide_id, slide_revision)
        if rendered is None:
            raise SlideRenderError(f"Renderer did not produce a PNG for slide index {slide_index}.")
        return rendered

    async def render_all(self) -> list[Path]:
        deck = self._load_deck()
        missing_indices = [
            index
            for index, slide in enumerate(deck.slides)
            if self.get_cached(slide.slide_id, self._slide_revision(slide, deck.revision)) is None
        ]
        if missing_indices:
            await self._render_indices(deck, missing_indices)

        return [
            self.get_cached(slide.slide_id, self._slide_revision(slide, deck.revision))
            for slide in deck.slides
        ]

    async def render_indices(self, slide_indices: list[int]) -> list[Path]:
        deck = self._load_deck()
        missing_indices = [
            index
            for index in slide_indices
            if self.get_cached(
                deck.slides[index].slide_id,
                self._slide_revision(deck.slides[index], deck.revision),
            )
            is None
        ]
        if missing_indices:
            await self._render_indices(deck, missing_indices)

        rendered_paths: list[Path] = []
        for index in slide_indices:
            slide = deck.slides[index]
            cached = self.get_cached(slide.slide_id, self._slide_revision(slide, deck.revision))
            if cached is None:
                raise SlideRenderError(f"Renderer did not produce a PNG for slide index {index}.")
            rendered_paths.append(cached)
        return rendered_paths

    def _load_deck(self) -> Deck:
        deck = read_deck(str(self.deck_path))
        manifest_path = resolve_manifest_path(str(self.deck_path), deck)
        if manifest_path is not None:
            deck.template_manifest = manifest_path
        return deck

    def _slide_revision(self, slide: Slide, deck_revision: int) -> int:
        return slide.revision or deck_revision

    def _cache_key(self, slide_id: str, revision: int) -> str:
        return f"{slide_id}:{revision}"

    async def _render_indices(self, deck: Deck, slide_indices: list[int]) -> None:
        if not self.is_available:
            raise SlideRenderError("LibreOffice preview dependencies are not available.")
        if not slide_indices:
            return

        async with self._lock:
            await asyncio.to_thread(self._render_indices_sync, deck, slide_indices)

    def _render_indices_sync(self, deck: Deck, slide_indices: list[int]) -> None:
        assert self.soffice_path is not None
        assert self.pdftoppm_path is not None

        with tempfile.TemporaryDirectory(prefix="agent-slides-render-", dir=self.cache_dir) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            pptx_path = tmp_dir / f"{self.deck_path.stem}-{deck.revision}.pptx"
            pdf_path = tmp_dir / f"{pptx_path.stem}.pdf"
            profile_dir = tmp_dir / "libreoffice-profile"
            profile_dir.mkdir()

            write_pptx(deck, str(pptx_path), asset_base_dir=self.deck_path.parent)

            soffice_result = subprocess.run(
                [
                    self.soffice_path,
                    f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                    "--headless",
                    "--convert-to",
                    "pdf:impress_pdf_Export",
                    "--outdir",
                    str(tmp_dir),
                    str(pptx_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if soffice_result.returncode != 0 or not pdf_path.exists():
                raise SlideRenderError(
                    "LibreOffice failed to render preview PDF: "
                    f"{(soffice_result.stderr or soffice_result.stdout).strip()}"
                )

            for slide_index in slide_indices:
                slide = deck.slides[slide_index]
                slide_revision = self._slide_revision(slide, deck.revision)
                output_prefix = tmp_dir / f"slide-{slide_index + 1}"
                png_path = self.cache_dir / f"{slide.slide_id}-{slide_revision}.png"

                pdftoppm_result = subprocess.run(
                    [
                        self.pdftoppm_path,
                        "-png",
                        "-r",
                        str(self._resolution),
                        "-f",
                        str(slide_index + 1),
                        "-l",
                        str(slide_index + 1),
                        str(pdf_path),
                        str(output_prefix),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                rendered_path = output_prefix.with_name(f"{output_prefix.name}-{slide_index + 1}.png")
                if pdftoppm_result.returncode != 0 or not rendered_path.exists():
                    raise SlideRenderError(
                        "pdftoppm failed to render preview PNG: "
                        f"{(pdftoppm_result.stderr or pdftoppm_result.stdout).strip()}"
                    )

                shutil.copyfile(rendered_path, png_path)
                self._rendered[self._cache_key(slide.slide_id, slide_revision)] = png_path
