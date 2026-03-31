---
name: create-deck
description: Build consulting-grade presentations from a natural-language brief using a 4-phase Pre-flight -> Storyline Review -> Build -> QA workflow on top of the agent-slides CLI.
---

# Create Deck

Use this skill when the user asks for a new presentation, deck, or slide narrative from scratch.

In this repo, prefer `uv run agent-slides ...` so the command uses the checked-out CLI.
Use `uv run agent-slides contract` as the canonical source for command semantics, mutation names, JSON outputs, and error codes.
Do not restate or invent design rules here. Design rules live in `config/design_rules/` and are enforced by `agent-slides validate`.
Story structure rules live in `${CLAUDE_SKILL_DIR}/references/storytelling.md`. Follow that guide for Pyramid Principle, SCQA flow, action titles, WWWH framing, and the five pre-flight questions.

This skill is not just CLI orchestration. It is responsible for presentation quality, storyline quality, and final QA.

## Required References

Load these references at the point they matter:

Repo-relative reference paths:

- `references/storytelling.md`
- `references/layout-selection.md`
- `references/chart-guide.md`
- `references/common-mistakes.md`

- Phase 0: no extra references required beyond asking the questions cleanly
- Before Phase 1, read `${CLAUDE_SKILL_DIR}/references/storytelling.md` and `${CLAUDE_SKILL_DIR}/references/layout-selection.md` (required: contains the full layout catalog with slot mappings and width limits)
- Before Phase 2, read `${CLAUDE_SKILL_DIR}/references/layout-selection.md` (re-read) and `${CLAUDE_SKILL_DIR}/references/content-density.md`
- Before adding a chart in Phase 2, read `${CLAUDE_SKILL_DIR}/references/chart-guide.md`
- Before Phase 3, read `${CLAUDE_SKILL_DIR}/references/common-mistakes.md`

Treat those references as part of the operating instructions for both this skill and the conversational deck orchestrator.
The shorthand reference paths are `references/storytelling.md`, `references/layout-selection.md`, `references/chart-guide.md`, and `references/common-mistakes.md`.

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

- Initialize the deck with `--template` when specified in the brief, otherwise use `--theme`.
- Use `slide add`, `slot set`, `slot clear`, `slot bind`, `chart add`, and `batch` as appropriate.
- Use explicit `--layout` for every slide when working with a template. Auto-layout does not know template slot structures.
- Follow the layout variety rule from `${CLAUDE_SKILL_DIR}/references/layout-selection.md`.
- Fill all planned content, including charts, images, and sources.
- Do not leave placeholder thinking in the deck. Finish the slide content fully.

### Template slot awareness (CRITICAL for template decks)

Before building with a template, run `uv run agent-slides inspect <manifest>` and read `${CLAUDE_SKILL_DIR}/references/layout-selection.md` which contains the full slot table.

Key rules:

- **Run `inspect` first.** Run `uv run agent-slides inspect <manifest>` and use the per-layout `has_body`, `max_heading_words`, `body_max_bullets`, and `width_class` fields to guide every slot decision. Do not guess layout constraints.
- **Set body on every layout where `has_body: true`.** Do NOT set body where `has_body` is false.
- **Scale body density to `body_max_bullets`.** Dense (6): 4-6 bullets. Medium (4): 3-4 bullets. Light (3): 2-3 bullets. Minimal (2): 1-2 short bullets.
- **Respect `max_heading_words` strictly.** Long headings on narrow layouts will overflow or shrink to unreadable sizes.
- **Source lines go FIRST in body content.** Place `Source: ...` as the FIRST text block in the body, before bullet points. Example: `[{"type":"paragraph","text":"Source: McKinsey, 2025"},{"type":"bullet","text":"Key finding 1"},...]`
- **Plan source lines in Phase 1.** Mark which slides get source lines. Use layouts where `has_body` is true.
- **BAN topic-label titles.** Every title must be an action statement. NEVER: "Market Overview". ALWAYS: "Market share fell 15% after competitor undercut pricing".
- **CRITICAL: Keep headings SHORT (6-10 words).** Template heading placeholders are typically short. Headings over 50 characters will overflow. Write the conclusion concisely: "Revenue grew 12% YoY to EUR 847M" not "The company achieved strong revenue growth of 12% year over year reaching EUR 847M".
- **Word count limits for body:** check `body_max_bullets` from inspect. Max 100 words for dense layouts, 40-60 for medium.

### Practical build sequence

1. If template: `uv run agent-slides init deck.json --template <pptx_or_manifest> --rules default`
   If theme: `uv run agent-slides init deck.json --theme <theme> --rules default`
2. Run `uv run agent-slides inspect <manifest>` to confirm slot structures.
3. Add each slide with explicit `--layout`.
4. Set slot content matching each layout's slot structure.
5. For image layouts, use real images from `examples/images/` (check `index.json` for tags).
6. Prefer `batch` for multi-slide creation when possible.
7. If a slide needs a chart, read `${CLAUDE_SKILL_DIR}/references/chart-guide.md` first.
8. Build only after validation passes.

### Layout guidance for template decks

Run `uv run agent-slides inspect <manifest>` and use the `categories` field to pick layouts:

- **Opener**: pick from layouts with a `subheading` slot (usually the first layout)
- **Dense content**: pick from `full_width_with_body` category (largest body area)
- **Key insight / highlight**: pick from `medium_with_body` category (emphasis + supporting points)
- **Bold statement / section break**: pick from `heading_only` category (heading IS the message)
- **Image slides**: pick from `image_layouts` category (heading + image)
- **Short callout**: pick from `narrow_with_body` category (1-2 compact bullets)

Use the per-layout `max_heading_words` and `body_max_bullets` to size content.
Alternate between light-background and colored-background layouts for visual variety.

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
6. When the user wants live review, run `uv run agent-slides preview deck.json --background` and open that URL for the user immediately.

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
