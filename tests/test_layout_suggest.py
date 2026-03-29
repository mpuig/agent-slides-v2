from __future__ import annotations

import pytest

from agent_slides.engine.layout_suggest import (
    _analyze_content,
    _group_blocks_by_heading,
    suggest_layouts,
)
from agent_slides.model import LayoutHints, NodeContent, TextBlock, load_design_rules


def make_content(*blocks: tuple[str, str]) -> NodeContent:
    return NodeContent(
        blocks=[TextBlock(type=block_type, text=text) for block_type, text in blocks]
    )


@pytest.mark.parametrize(
    ("content", "image_count", "expected_layout", "expected_score"),
    [
        (
            make_content(
                ("heading", "Product launch"),
                ("paragraph", "A concise overview of the launch story."),
            ),
            2,
            "gallery",
            0.95,
        ),
        (
            make_content(
                ("heading", "Product launch"),
                ("paragraph", "A concise overview of the launch story."),
            ),
            1,
            "image_left",
            0.9,
        ),
        (NodeContent(), 1, "hero_image", 0.9),
        (NodeContent(), 0, "blank", 0.8),
        (
            make_content(
                ("heading", "Quarterly update"),
                ("paragraph", "Three wins, one focus."),
            ),
            0,
            "title",
            0.9,
        ),
        (
            make_content(
                ("heading", "Quarterly update"),
                ("paragraph", "Revenue expanded across enterprise, self-serve, and partner channels this quarter."),
            ),
            0,
            "title_content",
            0.85,
        ),
        (
            make_content(
                ("heading", "Two bets"),
                ("paragraph", "Adoption climbed steadily across the existing customer base this quarter."),
                ("paragraph", "Pipeline grew materially after the new pricing and onboarding changes."),
            ),
            0,
            "two_col",
            0.9,
        ),
        (
            make_content(
                ("heading", "Three pillars"),
                ("paragraph", "Speed improved for onboarding, drafting, and presentation export flows."),
                ("paragraph", "Quality improved through stronger validation, retries, and layout scoring."),
                ("paragraph", "Reach improved through templates, previews, and collaboration tooling."),
            ),
            0,
            "three_col",
            0.9,
        ),
        (
            make_content(
                ("heading", "Platform choices"),
                ("heading", "Build"),
                ("paragraph", "Faster setup and lower fixed costs for the first release."),
                ("heading", "Buy"),
                ("paragraph", "Less control but shorter time to adoption for commodity needs."),
            ),
            0,
            "comparison",
            0.9,
        ),
        (
            make_content(
                ("heading", "Highlights"),
                ("bullet", "Revenue up"),
                ("bullet", "Costs down"),
                ("bullet", "NPS higher"),
                ("bullet", "Launch ready"),
            ),
            0,
            "title_content",
            0.8,
        ),
        (
            make_content(
                ("heading", "Backlog"),
                ("bullet", "Inbox zero"),
                ("bullet", "Templates"),
                ("bullet", "Analytics"),
                ("bullet", "Export"),
                ("bullet", "Search"),
                ("bullet", "Sharing"),
            ),
            0,
            "two_col",
            0.7,
        ),
        (
            make_content(
                ("paragraph", "A standalone paragraph should fall back to a generic content layout."),
            ),
            0,
            "title_content",
            0.5,
        ),
    ],
)
def test_suggest_layouts_returns_expected_top_rule(
    content: NodeContent,
    image_count: int,
    expected_layout: str,
    expected_score: float,
) -> None:
    suggestions = suggest_layouts(content, image_count=image_count)

    assert suggestions
    assert suggestions[0].layout == expected_layout
    assert suggestions[0].score == pytest.approx(expected_score)


def test_suggest_layouts_returns_ranked_unique_suggestions() -> None:
    suggestions = suggest_layouts(
        make_content(
            ("heading", "Quarterly update"),
            ("paragraph", "Revenue expanded across enterprise, self-serve, and partner channels this quarter."),
        )
    )

    assert [suggestion.layout for suggestion in suggestions] == ["title_content"]
    assert suggestions[0].reason == "A heading with one paragraph fits a title-and-content slide."


def test_suggest_layouts_filters_to_available_layouts_only() -> None:
    suggestions = suggest_layouts(
        make_content(
            ("heading", "Quarterly update"),
            ("paragraph", "Three wins, one focus."),
        ),
        available_layouts=["blank", "title_content"],
    )

    assert [suggestion.layout for suggestion in suggestions] == ["title_content"]
    assert suggestions[0].score == pytest.approx(0.5)


def test_suggest_layouts_never_auto_suggests_quote_or_closing() -> None:
    suggestions = suggest_layouts(
        make_content(
            ("heading", "Quarterly update"),
            ("paragraph", "Three wins, one focus."),
        ),
        available_layouts=["quote", "closing", "title"],
    )

    assert [suggestion.layout for suggestion in suggestions] == ["title"]


def test_suggest_layouts_uses_configurable_thresholds() -> None:
    custom_rules = load_design_rules("default").model_copy(
        update={
            "layout_hints": LayoutHints(
                max_bullets_for_single_column=3,
                equal_length_threshold=0.2,
                short_text_threshold=5,
            )
        }
    )

    short_text_suggestions = suggest_layouts(
        make_content(
            ("heading", "Quarterly update"),
            ("paragraph", "Three wins and one focus."),
        ),
        rules=custom_rules,
    )
    bullet_suggestions = suggest_layouts(
        make_content(
            ("heading", "Highlights"),
            ("bullet", "Revenue up"),
            ("bullet", "Costs down"),
            ("bullet", "NPS higher"),
            ("bullet", "Launch ready"),
        ),
        rules=custom_rules,
    )
    unequal_columns = suggest_layouts(
        make_content(
            ("heading", "Two bets"),
            ("paragraph", "Steady adoption across the existing enterprise install base."),
            (
                "paragraph",
                "Pipeline grew sharply after pricing changes, onboarding fixes, and channel expansion work.",
            ),
        ),
        rules=custom_rules,
    )

    assert short_text_suggestions[0].layout == "title_content"
    assert short_text_suggestions[0].score == pytest.approx(0.85)
    assert bullet_suggestions[0].layout == "two_col"
    assert bullet_suggestions[0].score == pytest.approx(0.7)
    assert unequal_columns[0].layout == "title_content"
    assert unequal_columns[0].score == pytest.approx(0.5)


def test_group_blocks_by_heading_splits_on_heading_boundaries() -> None:
    blocks = [
        TextBlock(type="heading", text="Left"),
        TextBlock(type="paragraph", text="Left body"),
        TextBlock(type="heading", text="Right"),
        TextBlock(type="paragraph", text="Right body"),
    ]

    groups = _group_blocks_by_heading(blocks)

    assert [[block.text for block in group] for group in groups] == [
        ["Left", "Left body"],
        ["Right", "Right body"],
    ]


def test_analyze_content_tracks_heading_and_group_metadata() -> None:
    content = make_content(
        ("heading", "Platform choices"),
        ("heading", "Build"),
        ("paragraph", "Faster setup and lower fixed costs."),
        ("heading", "Buy"),
        ("paragraph", "Less control but shorter time to adoption."),
    )

    profile = _analyze_content(content)

    assert profile.block_count == 5
    assert profile.word_count == 17
    assert profile.heading_count == 3
    assert len(profile.remaining_groups) == 2


def test_suggest_layouts_excludes_image_layouts_when_no_images() -> None:
    content = make_content(
        ("heading", "Product launch"),
        ("paragraph", "A concise overview of the launch story and results."),
    )
    suggestions_with_images = suggest_layouts(content, image_count=1)
    suggestions_no_images = suggest_layouts(content, image_count=0)

    image_layouts = {"gallery", "image_left", "image_right", "hero_image"}
    with_image_names = {s.layout for s in suggestions_with_images}
    no_image_names = {s.layout for s in suggestions_no_images}

    assert with_image_names & image_layouts, "image layouts should appear when images are available"
    assert not (no_image_names & image_layouts), "image layouts should not appear when image_count=0"
