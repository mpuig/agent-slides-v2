from pathlib import Path
from importlib import resources

import pytest

from agent_slides import AgentSlidesError
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import DesignRules, list_design_rules, load_design_rules
import agent_slides.model.design_rules as design_rules_module


def test_load_default_design_rules() -> None:
    rules = load_design_rules("default")

    assert isinstance(rules, DesignRules)
    assert rules.name == "default"
    assert rules.content_limits.max_bullets_per_slide == 6
    assert rules.overflow_policy.strategy == "shrink"
    assert rules.normalize_font_sizes is True
    assert rules.type_ladders["heading"] == [36.0, 32.0, 28.0, 24.0]
    assert rules.layout_hints.max_bullets_for_single_column == 5
    assert rules.layout_hints.equal_length_threshold == 0.4
    assert rules.layout_hints.short_text_threshold == 10
    assert rules.block_spacing.heading_to_paragraph == 12.0
    assert rules.block_spacing.bullet_to_bullet == 4.0


def test_load_nonexistent_design_rules_raises() -> None:
    with pytest.raises(AgentSlidesError, match="nonexistent"):
        load_design_rules("nonexistent")


def test_list_design_rules() -> None:
    assert list_design_rules() == ["default"]


def test_constraint_model_creation() -> None:
    constraint = Constraint(
        code="OVERFLOW",
        severity="warning",
        message="Slide body exceeds allowed bounds.",
        slide_id="slide-1",
        node_id="node-2",
    )

    assert constraint.code == "OVERFLOW"
    assert constraint.severity == "warning"
    assert constraint.slide_id == "slide-1"
    assert constraint.node_id == "node-2"


def test_design_rules_resource_is_packaged() -> None:
    resource = resources.files("agent_slides.config.design_rules").joinpath("default.yaml")

    assert resource.is_file()
    assert "name: default" in resource.read_text(encoding="utf-8")


def test_load_invalid_design_rules_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    invalid_profile = tmp_path / "broken.yaml"
    invalid_profile.write_text("name: broken\ncontent_limits: {}\n", encoding="utf-8")

    monkeypatch.setattr(design_rules_module, "_design_rules_dir", lambda: tmp_path)

    with pytest.raises(AgentSlidesError, match="broken"):
        load_design_rules("broken")
