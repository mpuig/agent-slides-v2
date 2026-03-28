---
name: create-deck
description: Build consulting-grade presentations from a natural-language brief using a 4-phase Pre-flight -> Storyline Review -> Build -> QA workflow on top of the agent-slides CLI.
---

# Create Deck

Use this skill when the user asks for a new presentation, deck, or slide narrative from scratch.

In this repo, prefer `uv run agent-slides ...` so the command uses the checked-out CLI.
Do not restate or invent design rules here. Design rules live in `config/design_rules/` and are enforced by `agent-slides validate`.
Story structure rules live in `${CLAUDE_SKILL_DIR}/references/storytelling.md`. Follow that guide for Pyramid Principle, SCQA flow, action titles, WWWH framing, and the five pre-flight questions.

This skill is not just CLI orchestration. It is responsible for presentation quality, storyline quality, and final QA.

## Required References

Load these references at the point they matter:

- Phase 0: no extra references required beyond asking the questions cleanly
- Before Phase 1, read `${CLAUDE_SKILL_DIR}/references/storytelling.md`
- Before locking or overriding layouts in Phase 1 or Phase 2, read `${CLAUDE_SKILL_DIR}/references/layout-selection.md`
- Before Phase 2, read `${CLAUDE_SKILL_DIR}/references/content-density.md`
- Before adding a chart in Phase 2, read `${CLAUDE_SKILL_DIR}/references/chart-guide.md`
- Before Phase 3, read `${CLAUDE_SKILL_DIR}/references/common-mistakes.md`

Treat those references as part of the operating instructions for both this skill and the conversational deck orchestrator.

## Workflow Overview

Run the work in four phases:

1. Pre-flight
2. Storyline Review
3. Build
4. QA

Do not skip Storyline Review. Do not build a full deck until the narrative is coherent.

## Phase 0: Pre-flight Questioning

Before touching the CLI, clarify the story inputs that determine deck quality.

Mode detection:

- If the user says "just do it", skip questions, infer reasonable defaults, and state the assumptions briefly.
- For a quick deck of about 5 slides, ask only:
  1. objective
  2. recommendation
- For a strategy deck of 8 or more slides, ask all five:
  1. audience
  2. objective
  3. recommendation
  4. scope
  5. target slide count

Questioning rules:

- Ask one question at a time, not as a survey dump.
- Challenge vague premises before moving on.
- If one or two answers are missing, infer the smallest reasonable assumption and say so.
- Never default to a neutral summary when the recommendation is missing. Propose a recommendation candidate.

## Phase 1: Storyline Review

### Step 1: Build the storyline with the Pyramid Principle

Read `${CLAUDE_SKILL_DIR}/references/storytelling.md` and `${CLAUDE_SKILL_DIR}/references/layout-selection.md`, then draft the narrative in this order:

```text
Title: [Deck title]
Answer: [Core recommendation]
Arguments:
  1. [Supporting argument] -> Slides N-M
  2. [Supporting argument] -> Slides N-M
  3. [Supporting argument] -> Slides N-M
```

Planning rules:

- Start with the answer, not the background.
- Organize the deck as answer -> 2-4 supporting arguments -> evidence.
- Give each content slide one message and an action title that states the takeaway.
- Default to 5 slides for a simple topic, 8-10 for strategy, and 15+ only when the brief clearly needs it.
- Usually keep slide 1 explicit as `title`.
- Usually keep the last slide explicit as `closing`.
- Default middle content slides to `--auto-layout` unless the structure is predetermined or you are correcting a weak auto-layout choice.

### Step 2: Create the slide-by-slide plan

For each slide, define:

- slide purpose
- action title
- key evidence or content
- target layout
- whether the slide should use `--auto-layout` or an explicit layout
- whether the slide needs a chart or image

Apply the Isomorphism Principle from `${CLAUDE_SKILL_DIR}/references/layout-selection.md`:

- Equal pillars or themes -> `three_col`
- Two contrasting approaches -> `two_col` or `comparison`
- Structured comparison with headers -> `comparison`
- Sequential narrative or one claim with proof -> `title_content`
- Data trend or composition -> `title_content` plus `chart_add`
- Key quote or statement -> `quote`

Flag these anti-patterns before building:

- Equal columns for unequal items
- The same layout on 3 or more consecutive slides
- A chart without a takeaway title and annotation

### Step 3: Challenge the storyline section by section

Review each argument before building:

- Does the argument support the answer?
- Are the slides under it sufficient evidence?
- Is each title an action title with a clear "so what"?
- Does the body content prove the title?
- Is the layout choice isomorphic to the content relationship?

Use stop points when something is weak:

- Raise one issue at a time.
- Fix gaps in the outline before generating commands.
- Turn uncovered messages into slides to add, not hand-wavy notes.

### Step 4: Produce the message coverage diagram

After the storyline draft, produce an ASCII coverage diagram:

```text
STORYLINE COVERAGE
===========================
[+] Deck: "[title]"
    |
    |-- [✓] Answer: "[core recommendation]"
    |
    |-- Argument 1: [name]
    |   |-- [✓] Slide 2: "[message]"
    |   `-- [GAP] Missing [evidence]
    |
    `-- Argument 2: [name]
        `-- [✓] Slide N: "[message]"
-------------------------
COVERAGE: X/Y messages covered (Z%)
GAPS: N ([gap names])
```

Coverage rules:

- Mark every answer, argument, and supporting message as covered or missing.
- Treat each `[GAP]` as a required slide or evidence insert.
- Use the coverage view to justify slide additions before build.

### Step 5: Stop for approval

Before Phase 2, present:

- the audience and objective you are optimizing for
- the top-level recommendation
- the storyline in Pyramid form
- the slide-by-slide plan with action titles and layouts
- the coverage diagram with explicit gaps

Ask for approval before building when the workflow is interactive.

### Step 6: Optional outside voice

After the storyline review, offer a second-opinion pass on the narrative.
If accepted, send the storyline to another model or agent and fold useful feedback back into the plan.

### Worked example

This is the quality bar for the output at the end of Phase 1.

Real pre-flight exchange:

```text
User: I need a five-slide CEO deck on why we should simplify SMB pricing next quarter.
Assistant: I recommend a decision deck that argues for a three-tier packaging reset because conversion friction matters more than preserving every legacy option.
User: Audience is the CEO and CRO, objective is approval for a Q3 pilot, and keep the scope to US self-serve SMB.
```

Real storyline plan:

```text
Title: SMB pricing simplification can raise conversion without sacrificing revenue
Answer: Approve a Q3 pilot that replaces the current menu with three packaged tiers for US self-serve SMB.

Slide 1 - title
Action title: SMB pricing simplification can raise conversion without sacrificing revenue
Purpose: Set the decision and audience context
Evidence/content: Decision statement, scope, pilot ask
Layout: title

Slide 2 - friction proof
Action title: The current pricing menu is suppressing trial-to-paid conversion at the moment of choice
Purpose: Show why the status quo is failing
Evidence/content: Funnel drop-off at pricing page, user confusion quotes, plan-count sprawl
Layout: title_content

Slide 3 - revenue risk reframed
Action title: Most revenue risk sits in discount leakage, not in removing low-value plan variants
Purpose: Defuse the main objection
Evidence/content: Discount depth by cohort, low attach rate of niche add-ons, retained ARPU scenarios
Layout: comparison

Slide 4 - proposed solution
Action title: A three-tier package structure matches buyer needs and keeps monetization levers intact
Purpose: Present the recommendation mechanics
Evidence/content: Good/better/best tier logic, feature migration rules, pricing fences
Layout: three_col

Slide 5 - closing
Action title: We should approve the Q3 pilot now so pricing can stop blocking SMB growth
Purpose: Land the decision and next steps
Evidence/content: Pilot scope, owners, success metrics, decision required today
Layout: closing
```

Real coverage diagram:

```text
STORYLINE COVERAGE
===========================
[+] Deck: "SMB pricing simplification can raise conversion without sacrificing revenue"
    |
    |-- [✓] Answer: "Approve a Q3 pilot that replaces the current menu with three packaged tiers for US self-serve SMB."
    |
    |-- Argument 1: Complexity is hurting conversion
    |   `-- [✓] Slide 2: "The current pricing menu is suppressing trial-to-paid conversion at the moment of choice"
    |
    |-- Argument 2: Revenue downside is manageable
    |   `-- [✓] Slide 3: "Most revenue risk sits in discount leakage, not in removing low-value plan variants"
    |
    |-- Argument 3: The new package design is executable
    |   `-- [✓] Slide 4: "A three-tier package structure matches buyer needs and keeps monetization levers intact"
    |
    `-- [GAP] Migration proof: no customer-support or billing-transition evidence yet
-------------------------
COVERAGE: 4/5 messages covered (80%)
GAPS: 1 (migration proof)
```

## Phase 2: Build

After the plan is approved, execute it through the CLI.
Read `${CLAUDE_SKILL_DIR}/references/content-density.md` before building so the slide structures, typography, spacing, and source treatment stay professional instead of defaulting to plain text blocks.

### Build rules

- Initialize the deck with a built-in theme.
- Use `slide add`, `slot set`, `slot clear`, `slot bind`, `chart add`, and `batch` as appropriate.
- Use `--auto-layout` where the content shape is clear from the payload and the layout does not need to be predetermined.
- Use explicit layouts for fixed-role slides such as `title`, `closing`, or when the structure is known in advance.
- Follow the layout variety rule from `${CLAUDE_SKILL_DIR}/references/layout-selection.md`.
- Fill all planned content, including charts, images, and sources.
- Do not leave placeholder thinking in the deck. Finish the slide content fully.

### Practical build sequence

1. `uv run agent-slides init deck.json --theme <theme> --rules default`
2. Add the opener and closer with explicit layouts.
3. Add content slides with `--auto-layout` or explicit `--layout` according to the approved plan.
4. Prefer one atomic `batch` payload for multi-slide creation and cleanup when possible.
5. If a slide needs a chart, read `${CLAUDE_SKILL_DIR}/references/chart-guide.md` first, then use `uv run agent-slides chart add ...`.
6. Build only after the deck content is complete and validated.

### Layout guidance during build

- `title` for the opener
- `closing` for the final recommendation or call to action
- `title_content` for a single claim with one supporting body area
- `two_col` or `comparison` for before/after, option A vs B, or trade-offs
- `three_col` for three pillars, steps, or lenses
- `quote` only for a genuinely important voice-of-customer or executive statement

If auto-layout chooses a weak structure, correct it with `slide set-layout`, then repair any unbound content.

## Phase 3: QA Review

Before QA, read `${CLAUDE_SKILL_DIR}/references/common-mistakes.md`.

### Required QA loop

1. Run `uv run agent-slides validate deck.json`.
2. Review the deck against the content QA checklist:
   - every content slide has an action title
   - body proves title on every slide
   - no slide has more than 6 bullets
   - no topic-label titles such as "Market Overview"
   - source lines are present for data claims
   - layout variety is used in 6+ slide decks
   - charts have both a title and a visible annotation or callout
3. Fix any issues.
4. Run `uv run agent-slides validate deck.json` again.
5. Only then build the `.pptx`.

If validation passes but the storytelling checklist fails, the deck is not done.

### Completion summary

Produce a final summary in this form:

```text
Deck QA Summary:
- Slides: N total (N content + title + closing)
- Action titles: N/N compliant
- Layout variety: N unique layouts
- Warnings: N from validate
- Gaps: N from coverage diagram
```

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

- Start with the recommendation or answer, not the background.
- If the brief is under-specified, ask or infer the five pre-flight inputs from `${CLAUDE_SKILL_DIR}/references/storytelling.md`: audience, objective, recommendation, scope, and target slide count.
- Organize the deck as answer -> 2-4 supporting arguments -> evidence.
- Give each content slide one message and an action title that states the takeaway.
- Default to 5 slides for a simple topic.
- Use 6-8 slides when the argument needs setup, comparison, and proof.
- Stay under 10 slides unless the user explicitly asks for more.
- Put one message on each slide.
- Prefer concise evidence over dense exposition.
- Use charts only when they clarify a claim better than text.
- Cite sources directly on the slide or in supporting text when the workflow supports it.

## Minimum Acceptable Output

A successful run of this skill produces:

- an approved storyline and slide-by-slide plan before build
- a message coverage diagram with explicit gaps
- a complete `deck.json`
- a clean or consciously resolved validation result
- a deck whose content slides use action titles
- a completion summary after QA
- a built `.pptx` when the user asks for output
