---
name: review-deck
description: Run rendered visual QA on an `agent-slides` deck using LibreOffice slide screenshots, a scored checklist, and optional auto-fixes for common issues.
---

# Review Deck

Use this skill when the user asks for deck QA, visual review, design review, screenshot-based critique, or wants to know whether a PPTX deck actually looks good after render.

In this repo, prefer `uv run agent-slides ...` so the checked-out CLI and assets are used.

This skill is the rendered counterpart to `agent-slides validate`. `validate` checks structural design rules. `review` checks the real rendered output.

## Tooling contract

This workflow depends on:

- `soffice` on `PATH`
- `pdftoppm` on `PATH`

The CLI command handles the rendering pipeline:

```bash
uv run agent-slides review deck.json
```

That command:

1. builds the deck to `.pptx`
2. renders the PPTX to PDF with LibreOffice headless
3. renders slide PNGs with `pdftoppm`
4. scores the deck against the visual QA checklist
5. writes `report.md`, `report.json`, and slide screenshots into `deck.review/` by default

## Core workflow

Run the work in four phases:

1. First impression
2. Slide-by-slide audit
3. Scored report
4. Optional auto-fix

## Phase 1: First impression

Start by running:

```bash
uv run agent-slides review deck.json
```

Read `report.md`, then inspect the title slide and 2-3 representative content-slide PNGs from the generated artifacts directory.

Capture three quick judgments in plain language:

- "The deck communicates ..."
- "The visual rhythm is ..."
- "If I had to grade this deck at a glance: ..."

Do not jump into detailed fixes until this gut read is clear.

## Phase 2: Slide-by-slide audit

Use the generated screenshots plus the structured report.

For each slide, inspect:

- visual hierarchy
- typography
- layout quality
- content quality

Use the rendered PNG as the source of truth for what the slide actually looks like.

Use this 38-item checklist directly during the audit:

1. Visual Hierarchy
- Title visually dominates (largest text, distinct from body)
- Clear reading order (title -> subheader -> body -> source)
- One focal point per slide
- White space is intentional
- Squint test: hierarchy visible when blurred
- Content doesn't touch slide edges
2. Typography
- Heading 24-44pt, body 10-18pt
- Sizes consistent across slides
- No more than 2 font families
- Bold used sparingly
- Text not truncated or overflowing
- Font readable at projection distance
3. Layout Quality
- Layout matches content relationship (isomorphism)
- Columns balanced in density
- Charts within slot bounds
- No excessive empty space
- Grid alignment consistent
- Image slots filled or intentionally empty
4. Content Quality
- Action title (complete sentence with "so what")
- NOT a topic label ("Market Overview" = fail)
- Body proves title
- No more than 6 bullets per slide
- Bullets concise (not paragraphs)
- Source lines for data claims
- Charts have title and labels
- Numbers rounded and readable
5. Deck-Level Patterns
- Layout variety (2+ layouts in 6+ slide decks)
- No 3+ consecutive same layout
- Title slide present
- Closing slide present
- Visual rhythm (mix of content types)
- Consistent theme throughout
6. AI Slop Detection
- Every slide same layout (no variety)
- Generic titles ("Introduction", "Overview", "Summary")
- Bullet walls on every slide
- Empty image/chart slots
- Inconsistent capitalization
- Repetitive auto-generated structure

Treat `report.json` as the machine baseline and the slide PNGs as the visual evidence.

## Phase 3: Scored report

Your output should summarize:

- category grades
- overall grade
- the top issues with screenshot evidence
- specific fixes that will materially improve the deck

Use this rubric for each category:

```text
A  = 0 failures in category
A- = 1 minor failure
B+ = 1 failure
B  = 2 failures
C+ = 3 failures
C  = 4+ failures
D  = majority of items fail
F  = category completely ignored
```

Calculate overall grade as a weighted average:

- Content Quality counts 2x
- AI Slop Detection counts 1.5x
- Visual Hierarchy, Typography, Layout Quality, and Deck-Level Patterns count 1x each

Prefer pointing to concrete slide files such as:

```text
[screenshot: deck.review/run/slides/slide-03.png]
```

If the user wants only the findings, stop here.

## Phase 4: Optional auto-fix

Only use auto-fix when the user explicitly wants fixes applied. The explicit approval path is:

```bash
uv run agent-slides review deck.json --fix
```

Use an iterative fix loop, not a single cleanup pass:

```text
Fix Loop (max 3 passes):
  Pass N:
    -> Fix top issue
    -> Re-render affected slide via LibreOffice
    -> Re-evaluate against checklist
    -> Pass? -> next issue
    -> Still failing after 2 attempts? -> flag as unresolvable, move on

  Stop early when: all categories B+ or above, or 3 passes complete
  Each fix produces a before/after PNG pair as evidence
```

Apply fixes in this priority order:

1. Content quality (action titles, body proves title)
2. Bullet count (split slides >6 bullets)
3. Missing elements (chart titles, source lines)
4. Layout variety (swap repeated layouts)
5. Visual issues (spacing, alignment)

Within that loop, prefer these common mechanical fixes when they match the top issue:

- rewrite generic topic-label titles using slide evidence when possible
- add missing chart titles
- add missing source lines for quantified claims
- split bullet-heavy `title_content` slides into a follow-up slide
- swap repeated layouts when deck-level monotony is dragging the grade
- rerender the deck and produce before/after comparison output for each fix

After `--fix`, inspect the new `after/` screenshots and compare the `before` and `after` grades in `report.json`.

## Working standard

A good run of this skill leaves behind:

- rendered slide PNGs
- a readable `report.md`
- a structured `report.json`
- screenshot-backed issue evidence
- before/after comparison artifacts when fixes are applied

If the render pipeline is unavailable, stop and report the missing tool exactly as the CLI surfaces it.
