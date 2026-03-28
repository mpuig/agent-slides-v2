---
name: create-deck
description: Build consulting-grade presentations from a natural-language brief using a 3-phase Plan -> Build -> QA workflow on top of the agent-slides CLI.
---

# Create Deck

Use this skill when the user asks for a new presentation, deck, or slide narrative from scratch.

In this repo, prefer `uv run agent-slides ...` so the command uses the checked-out CLI.

This skill is not just CLI orchestration. It is responsible for presentation quality, storyline quality, and final QA.

## Required References

Load these references at the point they matter:

- Before Phase 1, read `references/storytelling.md`.
- Before choosing or overriding layouts, read `references/layout-selection.md`.
- Before adding a chart, read `references/chart-guide.md`.
- Before Phase 3, read `references/common-mistakes.md`.

Treat those references as part of the operating instructions for both this skill and the conversational deck orchestrator.

## Workflow Overview

Run the work in three phases:

1. Plan
2. Build
3. QA

Do not skip Phase 1. Do not build a full deck until the storyline is coherent.

## Phase 1: Plan

### Step 1: Ask the pre-flight questions

Before touching the CLI, collect the inputs that determine deck quality:

- Audience: who will see this deck and what is their context?
- Objective: what decision, understanding, or action should the deck drive?
- Recommendation: what is the answer or point of view?
- Scope: what is in scope, out of scope, and what evidence is available?
- Length: how many slides or how much time does the user want?

If one or more of those answers are missing, stop and ask concise bundled questions before building.

### Step 2: Build the storyline with the Pyramid Principle

Read `references/storytelling.md`, then draft the argument in this order:

1. Answer first: the recommendation or takeaway.
2. Supporting arguments: the 2-4 reasons the answer is true.
3. Evidence: facts, examples, comparisons, or charts that prove each reason.

The deck should feel like one argument unfolding, not a pile of related slides.

### Step 3: Create the slide-by-slide plan

Read `references/layout-selection.md` before locking layouts.

For each slide, define:

- slide purpose
- action title
- key evidence or content
- target layout
- whether the slide should use `--auto-layout` or an explicit layout
- whether the slide needs a chart or image

Apply the isomorphism principle: the visual structure should match the shape of the idea.

Use layout variety deliberately. Do not repeat the same content layout over and over unless the repetition is part of the story.

### Step 4: Enforce action titles

Every content slide must have an action title that states the conclusion.

Good action title:

- "Automation cuts weekly reporting time by 60%"

Weak title:

- "Reporting Automation"

The body of the slide must prove the title, not merely relate to it.

### Step 5: Stop for approval

Before Phase 2, present the slide-by-slide plan and stop.

Include:

- the audience and objective you are optimizing for
- the top-level recommendation
- the storyline in Pyramid form
- the proposed slides with action titles and layouts

Ask for approval before building the deck.

## Phase 2: Build

After the plan is approved, execute it through the CLI.

### Build rules

- Initialize the deck with a built-in theme.
- Use `slide add`, `slot set`, `slot clear`, `slot bind`, `chart add`, and `batch` as appropriate.
- Use `--auto-layout` where the content shape is clear from the content payload and the layout does not need to be predetermined.
- Use explicit layouts for fixed-role slides such as `title`, `closing`, or when the structure is known in advance.
- Follow the layout variety rule from `references/layout-selection.md`.
- Fill all planned content, including charts, images, and sources.
- Do not leave placeholder thinking in the deck. Finish the slide content fully.

### Practical build sequence

1. `uv run agent-slides init deck.json --theme <theme> --rules default`
2. Add the opener and closer with explicit layouts.
3. Add content slides with `--auto-layout` or explicit `--layout` according to the approved plan.
4. Use `slot set` or one atomic `batch` payload to fill all text and image slots.
5. If a slide needs a chart, read `references/chart-guide.md` first, then use `uv run agent-slides chart add ...`.
6. Build only after the deck content is complete and validated.

### Layout guidance during build

- `title` for the opener.
- `closing` for the final recommendation or call to action.
- `title_content` for a single claim with one supporting body area.
- `two_col` or `comparison` for before/after, option A vs B, or trade-offs.
- `three_col` for three pillars, steps, or lenses.
- `quote` only for a genuinely important voice-of-customer or executive statement.

If auto-layout chooses a weak structure, correct it with `slide set-layout`, then repair any unbound content.

## Phase 3: QA

Before QA, read `references/common-mistakes.md`.

### Required QA loop

1. Run `uv run agent-slides validate deck.json`.
2. Review the deck against the common-mistakes checklist.
3. Check the storytelling standard:
   - Is every content title an action title?
   - Does the body prove the title?
   - Are sources present for factual claims, numbers, charts, and external visuals?
   - Does each slide advance the argument instead of repeating context?
4. Fix any issues.
5. Run `uv run agent-slides validate deck.json` again.
6. Only then build the `.pptx`.

If validation passes but the deck still fails the storytelling checklist, the deck is not done.

## CLI Surface To Use

Prefer the shipped repo commands rather than inventing alternate entry points:

- `uv run agent-slides init`
- `uv run agent-slides slide add`
- `uv run agent-slides slide set-layout`
- `uv run agent-slides slot set`
- `uv run agent-slides slot clear`
- `uv run agent-slides slot bind`
- `uv run agent-slides chart add`
- `uv run agent-slides batch`
- `uv run agent-slides validate`
- `uv run agent-slides build`
- `uv run agent-slides preview`

## Operational Defaults

- Default to 5 slides for a simple topic.
- Use 6-8 slides when the argument needs setup, comparison, and proof.
- Stay under 10 slides unless the user explicitly asks for more.
- Put one message on each slide.
- Prefer concise evidence over dense exposition.
- Use charts only when they clarify a claim better than text.
- Cite sources directly on the slide or in speaker-note-style supporting text if the workflow supports it.

## Minimum Acceptable Output

A successful run of this skill produces:

- an approved slide-by-slide plan before build
- a complete `deck.json`
- a clean or consciously resolved validation result
- a deck whose content slides use action titles
- a built `.pptx` when the user asks for output
