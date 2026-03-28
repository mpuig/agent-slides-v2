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

## Workflow Overview

Run the work in four phases:

1. First impression
2. Slide-by-slide audit
3. Scored report
4. Optional auto-fix

## CLI Surface To Use

Prefer the shipped repo commands rather than inventing alternate entry points:

- `uv run agent-slides review`
- `uv run agent-slides validate`
- `uv run agent-slides build`

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

Use the rendered PNG as the source of truth for what the slide actually looks like.

Treat `report.json` as the machine baseline and the slide PNGs as the visual evidence.

Inline the actual checklist. Evaluate each rendered slide against these items:

### 1. Visual Hierarchy (6 items)

- [ ] Title visually dominates (largest text, distinct from body)
- [ ] Clear reading order (title -> subheader -> body -> source)
- [ ] One focal point per slide (not competing elements)
- [ ] White space is intentional (breathing room, not emptiness)
- [ ] Squint test: hierarchy still visible when mentally blurred
- [ ] Content does not touch slide edges (margins respected)

### 2. Typography (6 items)

- [ ] Heading font size 24-44pt (consistent across deck)
- [ ] Body font size 10-18pt (readable, not cramped)
- [ ] Font sizes consistent across slides (same role = same size)
- [ ] No more than 2 font families used
- [ ] Bold used sparingly (headings yes, body sparingly)
- [ ] Text not truncated or overflowing visible area

### 3. Layout Quality (6 items)

- [ ] Layout matches content relationship (isomorphism)
- [ ] Columns are balanced (similar content density)
- [ ] Charts positioned within slot bounds (not overlapping text)
- [ ] No excessive empty space in content areas
- [ ] Grid alignment consistent (elements line up)
- [ ] Image slots either filled or intentionally empty

### 4. Content Quality (8 items)

- [ ] Title is an action title (complete sentence with "so what")
- [ ] Not a topic label ("Market Overview" -> fail)
- [ ] Body content proves the title claim
- [ ] No more than 6 bullets per slide
- [ ] Bullet text is concise (not full paragraphs)
- [ ] Source line present for data claims
- [ ] Chart has title and clear labels
- [ ] Numbers are rounded and readable (`$2.5B`, not `$2,487,392,104`)

### 5. Deck-Level (6 items)

- [ ] Layout variety (2+ layouts used in 6+ slide deck)
- [ ] No 3+ consecutive slides with same layout
- [ ] Title slide present
- [ ] Closing slide present
- [ ] Visual rhythm (mix of text, charts, images)
- [ ] Consistent theme (colors and fonts do not drift)

### 6. AI Slop (6 items)

- [ ] Deck avoids every-slide-the-same layout repetition
- [ ] Deck avoids generic titles ("Introduction", "Overview", "Summary")
- [ ] Deck avoids bullet walls (every slide is not just bullets)
- [ ] Deck avoids empty image or chart slots with no content
- [ ] Deck avoids inconsistent capitalization in titles
- [ ] Deck avoids auto-generated-looking repetition or vague claims

## Phase 3: Scored report

Your output should summarize:

- category grades
- overall grade
- the top issues with screenshot evidence
- specific fixes that will materially improve the deck

Use this rubric for every category:

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

Document the iterative fix loop explicitly:

```text
Fix Loop (max 3 passes):
  Pass N:
    -> Fix top issue
    -> Re-render affected slide
    -> Re-evaluate against checklist
    -> Pass? -> next issue
    -> Still failing after 2 attempts? -> flag as unresolvable, move on

  Stop when: all categories B+ or above, or 3 passes complete
```

Loop rules:

- Max 3 passes over the full deck
- Within each pass, max 2 attempts per issue before moving on
- Each fix produces a before/after PNG pair as evidence
- Stop early if all categories are B+ or above
- Never loop on subjective items only; prioritize concrete checklist failures

## Working standard

A good run of this skill leaves behind:

- rendered slide PNGs
- a readable `report.md`
- a structured `report.json`
- screenshot-backed issue evidence
- before/after comparison artifacts when fixes are applied

If the render pipeline is unavailable, stop and report the missing tool exactly as the CLI surfaces it.
