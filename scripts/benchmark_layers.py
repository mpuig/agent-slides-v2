"""Shared helpers for certification and demo benchmark layers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def run_dir_for(run_id: str) -> Path:
    return RUNS_DIR / run_id


def summary_path_for(run_id: str) -> Path:
    return run_dir_for(run_id) / "summary.json"


def demo_summary_path_for(run_id: str) -> Path:
    return run_dir_for(run_id) / "demo-summary.json"


def certification_summary_path_for(run_id: str) -> Path:
    return run_dir_for(run_id) / "certification" / "summary.json"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_run_summary(
    run_id: str,
    *,
    layer_name: str,
    layer_payload: dict[str, Any],
    top_level_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary_path = summary_path_for(run_id)
    summary = load_json(summary_path) or {"run_id": run_id}
    layers = summary.get("layers")
    if not isinstance(layers, dict):
        layers = {}
    layers[layer_name] = layer_payload
    summary["run_id"] = run_id
    summary["layers"] = layers
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    if top_level_updates:
        summary.update(top_level_updates)
    write_json(summary_path, summary)
    return summary
