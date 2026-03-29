"""Review command for rendered deck QA."""

from __future__ import annotations

import json
from pathlib import Path

import click

from agent_slides.review import review_deck


@click.command("review")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
)
@click.option("--dpi", type=int, default=200, show_default=True)
@click.option(
    "--fix",
    is_flag=True,
    default=False,
    help="Apply common auto-fixes before rerendering.",
)
def review_command(path: Path, output_dir: Path | None, dpi: int, fix: bool) -> None:
    """Render a deck to slide PNGs and score it against the visual QA checklist."""

    artifacts_dir = output_dir or path.parent / f"{path.stem}.review"
    report = review_deck(path, artifacts_dir, dpi=dpi, fix=fix)
    payload = {
        "ok": True,
        "data": {
            "output_dir": str(artifacts_dir),
            "report_path": report["report_path"],
            "report_json_path": report["report_json_path"],
            "overall_grade": report["active"]["overall"]["grade"],
            "slides": report["active"]["deck"]["slides"],
            "fixes_applied": len(report["fixes_applied"]),
        },
    }
    click.echo(json.dumps(payload))
