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

The checklist categories are:

1. Visual Hierarchy
2. Typography
3. Layout Quality
4. Content Quality
5. Deck-Level Patterns
6. AI Slop Detection

Treat `report.json` as the machine baseline and the slide PNGs as the visual evidence.

## Phase 3: Scored report

Your output should summarize:

- category grades
- overall grade
- the top issues with screenshot evidence
- specific fixes that will materially improve the deck

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

Current auto-fixes target common mechanical issues:

- rewrite generic topic-label titles using slide evidence when possible
- add missing chart titles
- split bullet-heavy `title_content` slides into a follow-up slide
- rerender the deck and produce before/after comparison output

After `--fix`, inspect the new `after/` screenshots and compare the `before` and `after` grades in `report.json`.

## Working standard

A good run of this skill leaves behind:

- rendered slide PNGs
- a readable `report.md`
- a structured `report.json`
- screenshot-backed issue evidence
- before/after comparison artifacts when fixes are applied

If the render pipeline is unavailable, stop and report the missing tool exactly as the CLI surfaces it.
