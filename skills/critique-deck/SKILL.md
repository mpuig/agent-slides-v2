---
name: critique-deck
description: Review an `agent-slides` deck for storytelling quality, narrative structure, message coverage, and content density without drifting into rendered visual QA.
---

# Critique Deck

Use this skill when the user asks whether a deck tells a good story, whether the narrative hangs together, whether the slide titles land the point, or whether the content supports the recommendation.

This skill is content QA, not visual QA.

- `critique-deck` = story, argument, evidence, and slide-message quality
- `review-deck` = rendered screenshots, visual checklist, and layout execution quality

In this repo, prefer `uv run agent-slides ...` plus the checked-in `deck.json` and related outputs instead of inventing alternate tooling.

## Relationship To Other Skills

- Run after `create-deck` or `edit-slide`, when slide content already exists.
- Run before or alongside `review-deck`.
- Use `agent-slides validate` for structural rule checks, not for story judgment.
- When the critique finds message or evidence gaps, feed those back into deck editing before spending time on visual polish.

## Required References

Load these references before scoring the deck:

- `${CLAUDE_SKILL_DIR}/../create-deck/references/storytelling.md`
- `${CLAUDE_SKILL_DIR}/../create-deck/references/common-mistakes.md`

Treat `storytelling.md` as the primary rulebook for Pyramid Principle, SCQA flow, action titles, and message-evidence structure.
Treat `common-mistakes.md` as the checklist for common deck-quality failure modes that show up as weak story structure, weak title discipline, or unsupported claims.

## Inputs To Review

Work from the strongest available source of truth, in this order:

1. A slide-by-slide storyline or outline from `create-deck` Phase 1
2. The checked-in `deck.json`
3. `uv run agent-slides info deck.json`
4. Optional rendered artifacts from `review-deck` only when they help confirm whether content relationships are being expressed clearly

Do not turn this into a screenshot-first workflow. If the core message is weak, call that out from the source content directly.

## Workflow Overview

Run the critique in five steps:

1. Load the storytelling references and identify the deck answer, arguments, and slide sequence.
2. Audit every slide against the five scoring dimensions below.
3. Produce the message coverage diagram.
4. Write a scored report with slide references and fix guidance.
5. If asked to improve the deck, fix the highest-leverage content issues before any visual QA pass.

## What To Check

Score five dimensions. Use slide numbers in every issue so the deck owner can act on the critique quickly.

### A. Action Titles

Check each slide title mechanically:

- Is the title a complete sentence with a clear "so what"?
- Can an executive understand the point from the title alone?
- Does the body content actually prove the title?
- Is the title short enough to read as one claim rather than two merged claims?
- If the title is a topic label, can it be rewritten into a conclusion backed by the slide evidence?

Flag as issues:

- topic labels such as "Market Context" or "Pricing Analysis"
- titles that summarize process instead of the takeaway
- titles that require the body to discover the point
- titles that overclaim relative to the evidence on the slide

### B. Narrative Flow

Check the deck-level storyline:

- Does the deck follow Pyramid Principle and lead with the answer?
- Does the opening establish SCQA cleanly and quickly?
- For decks with 8 or more slides, are section dividers used to mark argument shifts?
- Does the opening frame the problem or decision clearly?
- Does the closing land a recommendation, decision, or next step rather than trail off?
- Do slides appear in a logical order where each slide advances the argument instead of repeating or detouring?

Flag as issues:

- background before answer
- long context sections with no decision point
- sectionless long decks
- closing slides that summarize activity instead of making a recommendation
- orphan transitions where one slide does not logically lead to the next

### C. Isomorphism

Check whether the chosen content form matches the relationship being communicated:

- Are equal ideas shown with equal visual weight and parallel structure?
- Are comparisons shown in comparison layouts rather than as mixed prose?
- Is quantitative evidence shown as a chart, table, or structured comparison rather than buried in bullets?
- Do layout choices match the argument type: compare, rank, process, option set, evidence stack?
- If two items are contrasted, does the slide make the contrast explicit instead of implying it?

Flag as issues:

- unequal columns for equal options
- bullet lists used where a comparison or chart is the clearer form
- dense prose standing in for process, ranking, or before/after logic
- layouts that imply hierarchy when the content claims parity

### D. Content Density

Check whether each slide carries enough structured content to do real work without becoming overloaded:

- Does the slide have visual structure rather than plain text only?
- Does the content fill at least roughly 60% of the intended content area?
- Does the slide stay at 6 bullets or fewer?
- Is the information chunked into evidence blocks, comparisons, charts, tables, or grouped bullets rather than a wall of text?
- If a slide is sparse, is it intentionally sparse because it is a title or section divider?

Flag as issues:

- mostly empty slides that should carry evidence
- paragraph-heavy slides with no visible structure
- bullet floods with more than 6 bullets
- "note to self" slides that read like outline placeholders rather than presentation-ready content

### E. Coverage

Check whether the deck's arguments are fully supported:

- Does every major argument have at least one evidence slide behind it?
- Is every slide attached to the answer or one of the supporting arguments?
- Are there orphan slides that do not support any argument?
- Are there unsupported claims that need evidence, data, or an example slide?
- Is the deck missing a critical proof point needed to make the recommendation credible?

Treat every gap as a concrete action:

- add a slide
- add evidence to an existing slide
- move a slide under the correct argument
- cut the slide if it does not support the story

## Coverage Diagram Output

Produce the same ASCII-style coverage view used in `create-deck` Phase 1, but reconcile it against the actual current deck:

```text
STORYLINE COVERAGE
===========================
[+] Deck: "[deck answer]"
    |
    |-- [✓] Answer: "[core recommendation]"
    |
    |-- Argument 1: [name]
    |   |-- [✓] Slide 2: "[message]"
    |   `-- [GAP] Missing [evidence or support]"
    |
    |-- Argument 2: [name]
    |   `-- [✓] Slide 4: "[message]"
    |
    `-- [ORPHAN] Slide 6: "[message that does not support the answer]"
-------------------------
COVERAGE: X/Y messages covered (Z%)
GAPS: N ([gap names])
ORPHANS: N ([slide numbers])
```

Coverage rules:

- Mark the answer, each argument, and each key supporting message as covered, missing, or orphaned.
- Convert every `[GAP]` into a concrete missing proof point.
- Convert every `[ORPHAN]` into a move-or-cut decision.
- If the deck has no clear answer, state that directly before scoring coverage.

## Scoring Standard

Use this scale for each dimension:

- `5` = strong, executive-ready
- `4` = good, minor tightening needed
- `3` = mixed, noticeable issues
- `2` = weak, story problems are limiting the deck
- `1` = failing, major rewrite needed

Letter conversion:

- `4.5-5.0` = `A`
- `3.8-4.4` = `B`
- `3.0-3.7` = `C`
- `2.0-2.9` = `D`
- `<2.0` = `F`

## Report Format

Return a scored report in this shape:

```text
CRITIQUE-DECK REPORT
Deck: [title or file]
Overall Grade: [letter] ([score]/5)

A. Action Titles: [letter] ([score]/5)
- Slide N: [issue]
- Slide N: [issue]

B. Narrative Flow: [letter] ([score]/5)
- [deck-level issue]
- [slide transition issue]

C. Isomorphism: [letter] ([score]/5)
- Slide N: [issue]

D. Content Density: [letter] ([score]/5)
- Slide N: [issue]

E. Coverage: [letter] ([score]/5)
- [gap or orphan]

F. Final Verdict
- Best slide: [slide number and why]
- Biggest risk: [highest-leverage problem]
- Fix first: [single most important next edit]

[coverage diagram]
```

Report rules:

- Every issue must name the relevant slide number or say explicitly that it is deck-level.
- Keep findings specific and checkable, not vague style commentary.
- Prioritize issues that break the recommendation, argument flow, or evidence chain.
- Do not spend the report on pixel polish, alignment, or rendering artifacts. That belongs in `review-deck`.

## Working Standard

A good run of this skill leaves behind:

- a clear verdict on whether the deck tells a coherent story
- dimension scores with concrete slide references
- a coverage diagram showing gaps and orphan slides
- a short list of the highest-leverage content fixes

If the deck fails on answer-first narrative, unsupported claims, or weak action titles, say so plainly and recommend fixing those before any visual review pass.
