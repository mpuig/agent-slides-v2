from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "learn-template" / "SKILL.md"
CLAUDE_SKILL_PATH = ROOT / ".claude" / "skills" / "learn-template"


def test_learn_template_skill_documents_guided_workflow() -> None:
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    assert skill_text.startswith("---\nname: learn-template\n")
    assert "## Workflow Overview" in skill_text
    assert "1. Receive template" in skill_text
    assert "2. Learn" in skill_text
    assert "3. Inspect" in skill_text
    assert "4. Review" in skill_text
    assert "5. Edit manifest when needed" in skill_text
    assert "6. Test with a small deck" in skill_text
    assert "7. Confirm the rendered result" in skill_text
    assert "8. Hand off to `create-deck`" in skill_text
    assert "uv run agent-slides learn template.pptx -o manifest.json" in skill_text
    assert "uv run agent-slides inspect manifest.json" in skill_text
    assert "uv run agent-slides init test.json --template manifest.json" in skill_text
    assert "uv run agent-slides build test.json -o test.pptx" in skill_text
    assert "uv run agent-slides review test.json" in skill_text


def test_learn_template_skill_covers_review_rules_errors_and_handoff() -> None:
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    assert "heading`, `subheading`, `body`, `col1`, `col2`, `image`" in skill_text
    assert 'set `"usable": false` on layouts you want the CLI to ignore' in skill_text
    assert "Template file not found" in skill_text
    assert "0 usable layouts" in skill_text
    assert "template changed" in skill_text
    assert (
        '/create-deck --template manifest.json "make a deck about Q3 strategy"'
        in skill_text
    )
    assert CLAUDE_SKILL_PATH.is_symlink()
    assert CLAUDE_SKILL_PATH.resolve() == SKILL_PATH.parent.resolve()
