from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_slides.model.types import NodeContent

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_layout_fixtures.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "generate_layout_fixtures", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_inventory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "layouts": [
                    {
                        "slug": "title_only",
                        "testable": True,
                        "slot_structure": "heading_only",
                        "fillable_slots": ["heading", "subheading"],
                    },
                    {
                        "slug": "body_text",
                        "testable": True,
                        "slot_structure": "heading_body",
                        "fillable_slots": ["heading", "body"],
                    },
                    {
                        "slug": "visual_story",
                        "testable": True,
                        "slot_structure": "heading_image",
                        "fillable_slots": ["heading", "image"],
                    },
                    {
                        "slug": "mixed_story",
                        "testable": True,
                        "slot_structure": "heading_body_image",
                        "fillable_slots": ["heading", "body", "image"],
                    },
                    {
                        "slug": "three_up",
                        "testable": True,
                        "slot_structure": "multi_slot",
                        "fillable_slots": ["heading", "col1", "col2", "col3"],
                    },
                    {
                        "slug": "blankish",
                        "testable": False,
                        "slot_structure": "blank",
                        "fillable_slots": [],
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _validate_text_payloads(payload: dict[str, object]) -> None:
    for slot_name, slot_payload in payload.items():
        assert isinstance(slot_name, str)
        assert isinstance(slot_payload, dict)
        if "image_path" in slot_payload:
            image_path = ROOT / str(slot_payload["image_path"])
            assert image_path.is_file()
            continue
        validated = NodeContent.model_validate(slot_payload)
        assert validated.blocks


def test_generate_layout_fixtures_cli_writes_expected_fixture_files(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "layout-inventory.json"
    output_dir = tmp_path / "layout_cases"
    _write_inventory(inventory_path)

    result = _run_script(
        "--inventory", str(inventory_path), "--output", str(output_dir)
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["slot_structure_count"] == 5
    assert summary["written_files"] == [
        "heading_body.json",
        "heading_body_image.json",
        "heading_image.json",
        "heading_only.json",
        "multi_slot.json",
    ]

    heading_only = json.loads(
        (output_dir / "heading_only.json").read_text(encoding="utf-8")
    )
    assert set(heading_only) == {"long_heading", "narrow_safe", "nominal"}
    assert len(heading_only["long_heading"]["heading"]["blocks"][0]["text"]) > 80

    heading_body = json.loads(
        (output_dir / "heading_body.json").read_text(encoding="utf-8")
    )
    assert "dense_body" in heading_body
    assert len(heading_body["dense_body"]["body"]["blocks"]) >= 6

    heading_image = json.loads(
        (output_dir / "heading_image.json").read_text(encoding="utf-8")
    )
    assert {
        "image_present",
        "image_missing",
        "long_heading",
        "narrow_safe",
        "nominal",
    } == set(heading_image)
    assert "image" in heading_image["image_present"]
    assert "image" not in heading_image["image_missing"]

    for fixture_path in sorted(output_dir.glob("*.json")):
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        for variant_payload in payload.values():
            assert isinstance(variant_payload, dict)
            _validate_text_payloads(variant_payload)


def test_generate_layout_fixtures_is_deterministic(tmp_path: Path) -> None:
    inventory_path = tmp_path / "layout-inventory.json"
    first_output_dir = tmp_path / "first"
    second_output_dir = tmp_path / "second"
    _write_inventory(inventory_path)

    first = _run_script(
        "--inventory", str(inventory_path), "--output", str(first_output_dir)
    )
    second = _run_script(
        "--inventory", str(inventory_path), "--output", str(second_output_dir)
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    first_payloads = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(first_output_dir.glob("*.json"))
    }
    second_payloads = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(second_output_dir.glob("*.json"))
    }
    assert first_payloads == second_payloads


def test_build_fixture_payloads_rejects_inventory_without_testable_layouts(
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    inventory_path = tmp_path / "layout-inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "layouts": [
                    {"slug": "blank", "testable": False, "slot_structure": "blank"}
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not contain any testable layouts"):
        module.build_fixture_payloads(
            json.loads(inventory_path.read_text(encoding="utf-8"))
        )


def test_build_fixture_payloads_supports_blank_slot_structures() -> None:
    module = _load_script_module()
    inventory = {
        "layouts": [
            {
                "slug": "blank",
                "testable": True,
                "slot_structure": "blank",
                "fillable_slots": [],
            }
        ]
    }

    payloads = module.build_fixture_payloads(inventory)

    assert payloads == {"blank": {"blank": {}}}
