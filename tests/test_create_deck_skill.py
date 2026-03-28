from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "create-deck" / "SKILL.md"


def test_create_deck_skill_defines_four_phase_workflow() -> None:
    skill_text = SKILL_PATH.read_text()

    assert "Phase 0: Pre-flight Questioning" in skill_text
    assert "Phase 1: Storyline Review" in skill_text
    assert "Phase 2: Build" in skill_text
    assert "Phase 3: QA Review" in skill_text
    assert "If the user says \"just do it\", skip questions" in skill_text
    assert "For a quick deck of about 5 slides, ask only" in skill_text
    assert "For a strategy deck of 8 or more slides, ask all five" in skill_text


def test_create_deck_skill_covers_storyline_review_and_qa_outputs() -> None:
    skill_text = SKILL_PATH.read_text()

    assert "STORYLINE COVERAGE" in skill_text
    assert "[GAP]" in skill_text
    assert "Optional outside voice" in skill_text
    assert "Equal pillars or themes -> `three_col`" in skill_text
    assert "A chart without a takeaway title and annotation" in skill_text
    assert "Deck QA Summary:" in skill_text
    assert "`references/storytelling.md`" in skill_text
    assert "`references/layout-selection.md`" in skill_text
    assert "`references/chart-guide.md`" in skill_text
    assert "`references/common-mistakes.md`" in skill_text
