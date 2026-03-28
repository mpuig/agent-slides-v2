---
name: polish-deck
description: Run the final pre-share polish pass on an `agent-slides` deck. Checks structural completeness, source lines, formatting consistency, and content completeness, then applies only safe mechanical fixes.
---

# Polish Deck

Use this skill for the last deck pass before sharing. It catches completeness and consistency problems that `build`, `validate`, and rendered review often leave behind.

Run this skill last, after `create-deck`, `review-deck`, and any critique workflow already in use. It is a polish pass, not a narrative rewrite.

In this repo, prefer `uv run agent-slides ...` so the checked-out CLI and rules are used.

## What this skill is for

- final pass on deck source quality before sharing
- completeness and consistency checks that are still visible in `deck.json`
- conservative auto-fixes that do not change the story

## What this skill must not do

- do not rewrite the narrative or change the recommendation
- do not restructure the deck except for small mechanical repairs already implied by the content
- do not invent facts, sources, speaker notes, or metadata
- do not review speaker notes or presentation metadata; both are explicitly out of scope for `agent-slides` v0

## CLI Surface To Use

Prefer shipped commands over ad hoc scripts:

- `uv run agent-slides info`
- `uv run agent-slides validate`
- `uv run agent-slides build`
- `uv run agent-slides review` when rendered proof is needed

Use direct JSON inspection only when the CLI does not expose the needed detail cleanly.

## Workflow Overview

Run the work in four phases:

1. Pre-polish assessment
2. Checks and findings
3. Auto-fix pass
4. Final report

## Phase 1: Pre-polish assessment

Before fixing anything:

1. Inspect the deck structure with `uv run agent-slides info <deck.json>`.
2. Identify the current slide count, layouts, title slide, closing slide, and obvious empty slots.
3. Sample the deck for style patterns already in use:
   - title capitalization pattern
   - heading and body sizing pattern
   - bullet character pattern
   - source-line pattern
4. Decide what is safe to auto-fix versus what needs manual attention.

Record a short assessment:

- what already looks complete
- what categories need work
- whether the deck appears safe for mechanical fixes

## Phase 2: Checks and findings

Use this checklist directly and produce findings grouped by category.

### 1. Structural completeness

- [ ] First slide is a title slide
- [ ] Last slide is a closing slide
- [ ] Decks with more than 8 content slides include section dividers where topic shifts warrant them

### 2. Source lines on data slides

- [ ] Every slide with a chart includes a source line
- [ ] Every slide with a quantified claim, statistic, KPI, or market-size number includes a source line
- [ ] Source text is concise rather than paragraph-length
- [ ] Source formatting is consistent across the deck

Default source-line style:

```text
Source: <organization>, <year or period>
```

If the deck already uses a clear alternative such as `Sources:`, preserve the dominant deck pattern instead of forcing a new one.

### 3. Formatting consistency

- [ ] Same text role uses the same font size across slides when the deck pattern is clear
- [ ] Bullet style is consistent across slides
- [ ] Body text alignment is consistent; avoid mixed left/center alignment without a clear layout reason
- [ ] Slide titles use one capitalization style consistently: sentence case or title case

### 4. Content completeness

- [ ] Content slides do not leave visible slots empty without intent
- [ ] No placeholder text such as `Lorem ipsum`, `TBD`, or `TODO`
- [ ] Charts have titles
- [ ] Comparison layouts have roughly balanced content density between sides

## Phase 3: Auto-fix pass

Only apply fixes that are mechanical, low-risk, and supported by deck context.

Safe auto-fixes:

- add a missing source line when the source is already clear from the slide, deck, brief, or existing source pattern
- normalize source-line prefix and punctuation to the dominant deck style
- normalize slide-title capitalization to the dominant deck pattern when the intended casing is obvious
- replace placeholder strings such as `TBD` in a source line or chart title only when the correct text is already evident elsewhere in the deck
- fill a chart title when the chart topic is already stated by the slide title and the chart is the only data object on the slide

Do not auto-fix these without explicit user intent or unambiguous evidence:

- invent a missing source
- rewrite body copy to balance a comparison slide
- add new section-divider slides when the narrative grouping is unclear
- guess missing content for an empty visible slot
- change theme, layout family, or slide order

Auto-fix rules:

1. Prefer the smallest semantic mutation available through the CLI.
2. Re-run `uv run agent-slides info <deck.json>` or inspect the affected source after each meaningful fix batch.
3. Run `uv run agent-slides validate <deck.json>` after fixes.
4. If a fix depends on guessing, stop and mark it for manual attention instead of fabricating content.

## Phase 4: Final report

Finish with a concise report in this format:

```text
POLISH REPORT
Deck: <path>

Assessment
- <what was already solid>
- <scope of polish pass>

Findings
- Structural completeness:
  - [fixed] ...
  - [manual] ...
- Source lines:
  - [fixed] ...
  - [manual] ...
- Formatting consistency:
  - [fixed] ...
  - [manual] ...
- Content completeness:
  - [fixed] ...
  - [manual] ...

Auto-fixes applied
- <exact mechanical fix>

Manual attention required
- <items that need human judgment or missing facts>

Validation
- `uv run agent-slides validate <deck.json>`
- `uv run agent-slides build <deck.json>` when the edits affect rendered output
- `uv run agent-slides review <deck.json>` when screenshot proof is needed
```

Keep the report factual. Separate what was fixed from what was only observed.

## Relationship to other skills

- Run after `create-deck`; that skill builds the story and initial slide set.
- Run after `review-deck`; that skill checks rendered output, while `polish-deck` checks source completeness and consistency.
- If a critique workflow is also used, run `polish-deck` after critique so this skill can lock the final mechanical details.

## Decision rule

Stop the polish pass when both of these are true:

- all safe mechanical fixes have been applied
- every remaining finding requires human judgment, missing facts, or a narrative decision
