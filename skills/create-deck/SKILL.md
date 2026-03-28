---
name: create-deck
description: Orchestrate end-to-end deck creation from a natural-language brief using the agent-slides CLI. Use when asked to make a deck, presentation, or slide outline from a topic, and turn it into a validated deck JSON plus optional PPTX output.
---

# Create Deck

Use this skill when the user gives a topic such as "make a deck about X" and wants a complete presentation built with `agent-slides`.

Keep this skill focused on orchestration. Do not restate or invent design rules here. Design rules live in `config/design_rules/` and are enforced by `agent-slides validate`.
Story structure rules live in `references/storytelling.md`. Follow that guide for Pyramid Principle, SCQA flow, action titles, WWWH framing, and the five pre-flight questions.

## Workflow

Run this as a 4-phase workflow:

1. Phase 0: Pre-flight questioning.
2. Phase 1: Storyline review.
3. Phase 2: Build.
4. Phase 3: QA review.

If `agent-slides` is not already on `PATH`, run the same commands through the repo wrapper the project uses, for example `uv run agent-slides ...`.

## Phase 0: Pre-flight Questioning

Do not plan slides immediately. First clarify the story.

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

Phase 0 reference loading:

- No reference docs are required beyond asking the questions cleanly.

## Phase 1: Storyline Review

Before touching the CLI, read:

- `references/storytelling.md`
- `references/layout-selection.md`

Turn the brief into a recommendation-first storyline using the Pyramid Principle:

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
- Default middle content slides to `--auto-layout` unless the structure is predetermined or you are correcting a bad auto pick.

Challenge the storyline section by section before building:

- Does the argument support the answer?
- Are the slides under it sufficient evidence?
- Is each content title an action title with a verb and a clear "so what"?
- Does the body content prove the title?
- Is the layout choice isomorphic to the content relationship?

Use stop points when something is weak:

- Raise one issue at a time.
- Fix gaps in the outline before generating commands.
- Turn uncovered messages into slides to add, not hand-wavy notes.

Produce a message coverage diagram after the storyline draft:

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
- Ask for approval on the storyline and coverage before building when the workflow is interactive.

Optional outside voice:

- After the storyline review, offer a second-opinion pass on the narrative.
- If accepted, send the storyline to another model or agent and fold useful feedback back into the plan.

## Layout Selection Via Isomorphism

Use only built-in layouts that exist:

- `title`: title slide with `heading` and `subheading` slots. Aliases `title` and `subtitle` also work for slot setting.
- `title_content`: one heading plus one body area. Best default for explanation, agenda, summary, or a linear argument.
- `two_col`: one heading plus two body columns.
- `comparison`: `heading`, `left_header`, `left_body`, `right_header`, `right_body`.
- `three_col`: one heading plus three short columns.
- `quote`: `quote` plus `attribution`.
- `closing`: single `body` slot for final takeaway or call to action.
- `blank`: only when you intentionally need an empty slide.

Apply the Isomorphism Principle from `references/layout-selection.md`:

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

## Phase 2: Build

Before adding charts, read `references/chart-guide.md` if the plan includes data visualization.

Execution rules:

- Choose a theme and initialize the deck.
- Use explicit `--layout title` for the opener and `--layout closing` for the ending.
- Prefer `agent-slides slide add deck.json --auto-layout --content '...'` for content slides.
- Use `slide set-layout` only when the conceptual relationship or auto-layout result requires correction.
- Prefer one `batch` call for multi-slide creation and cleanup when possible.
- Add charts where the storyline calls for data proof.
- In decks longer than 6 slides, use at least 2 to 3 layouts.

## Phase 3: QA Review

Before the QA pass, read `references/common-mistakes.md`.

Run the QA in this order:

1. `agent-slides validate deck.json`
2. Content QA checklist:
   - every content slide has an action title
   - body proves title on every slide
   - no slide has more than 6 bullets
   - no topic-label titles such as "Market Overview"
   - source lines are present for data claims
   - layout variety is used in 6+ slide decks
   - charts have both a title and a visible annotation or callout
3. Completion summary:

```text
Deck QA Summary:
- Slides: N total (N content + title + closing)
- Action titles: N/N compliant
- Layout variety: N unique layouts
- Warnings: N from validate
- Gaps: N from coverage diagram
```

## Choose a Theme

Start with a built-in theme instead of inventing one:

```bash
agent-slides theme list
```

Practical defaults:

- `default`: safe general-purpose choice
- `corporate`: formal business deck
- `startup`: more energetic pitch-style deck
- `academic`: sober / lecture style
- `dark`: dark-room presentation

Pick the theme from audience and setting, not from ad hoc style rules in the skill.

## Initialize the Deck

Initialize a new sidecar JSON file with the chosen theme and the default ruleset:

```bash
agent-slides init deck.json --theme startup --rules default
```

## Add Slides

Create slides in outline order:

```bash
agent-slides slide add deck.json --layout title
agent-slides slide add deck.json --auto-layout --content '{"blocks":[{"type":"heading","text":"Why teams are experimenting now"},{"type":"bullet","text":"Faster drafting"},{"type":"bullet","text":"Better repetitive-task coverage"},{"type":"bullet","text":"Lower cost to test ideas"}]}'
agent-slides slide add deck.json --auto-layout --content '{"blocks":[{"type":"heading","text":"Human-only vs agent-assisted"},{"type":"paragraph","text":"Human-only: Strong judgment and slower first pass."},{"type":"paragraph","text":"Agent-assisted: Faster iteration but needs review."}]}'
agent-slides slide add deck.json --auto-layout --content '{"blocks":[{"type":"heading","text":"Adoption rule"},{"type":"paragraph","text":"Use agents to widen the first draft, then review with human judgment."}]}'
agent-slides slide add deck.json --layout closing
```

When `--auto-layout` succeeds, it both selects the layout and pre-fills matching slots. Use that as the default for slide 2 onward unless the slide has an obvious fixed role such as `title` or `closing`.

## Fallback When Auto-Layout Picks Wrong

Treat auto-layout as the first pass, not the last word:

1. Create the content slide with `--auto-layout --content '...'`.
2. Read the command output to see the chosen `layout`, `auto_selected: true`, and selection `reason`.
3. Validate or preview the deck.
4. If the structure is wrong, switch the slide explicitly with `slide set-layout`.
5. Re-check for `UNBOUND_NODES`, then refill or rebind any slots that no longer map cleanly.

Example fallback:

```bash
agent-slides slide add deck.json --auto-layout --content '{"blocks":[{"type":"heading","text":"Human-only vs agent-assisted"},{"type":"paragraph","text":"Human-only: Strong judgment and slower first pass."},{"type":"paragraph","text":"Agent-assisted: Faster iteration but needs review."}]}'
agent-slides slide set-layout deck.json --slide 2 --layout comparison
agent-slides slot set deck.json --slide 2 --slot left_header --text "Human-only"
agent-slides slot set deck.json --slide 2 --slot left_body --text "- Strong judgment\n- Slower first pass"
agent-slides slot set deck.json --slide 2 --slot right_header --text "Agent-assisted"
agent-slides slot set deck.json --slide 2 --slot right_body --text "- Faster iteration\n- Needs review"
```

## Fill Content

For one-off edits, use `slot set`:

```bash
agent-slides slot set deck.json --slide 0 --slot title --text "AI Agents for Product Teams"
agent-slides slot set deck.json --slide 0 --slot subtitle --text "Where they help, where they fail, and how to adopt them"
agent-slides slot set deck.json --slide 1 --slot heading --text "Why teams adopt them"
agent-slides slot set deck.json --slide 1 --slot body --text "- Faster first drafts\n- Better task coverage\n- Lower coordination cost"
```

Prefer one `batch` call when creating a full deck. It is more efficient and applies all operations atomically.

Example 5-slide batch that validates cleanly:

```bash
cat <<'JSON' | agent-slides batch deck.json
[
  {"command": "slide_add", "args": {"layout": "title"}},
  {"command": "slide_add", "args": {"auto_layout": true, "content": {"blocks": [
    {"type": "heading", "text": "Why teams are experimenting now"},
    {"type": "bullet", "text": "Faster drafting"},
    {"type": "bullet", "text": "Better repetitive-task coverage"},
    {"type": "bullet", "text": "Lower cost to test ideas"}
  ]}}},
  {"command": "slide_add", "args": {"auto_layout": true, "content": {"blocks": [
    {"type": "heading", "text": "Human-only vs agent-assisted"},
    {"type": "paragraph", "text": "Human-only: Strong judgment and slower first pass."},
    {"type": "paragraph", "text": "Agent-assisted: Faster iteration but needs review."}
  ]}}},
  {"command": "slide_add", "args": {"auto_layout": true, "content": {"blocks": [
    {"type": "heading", "text": "Adoption rule"},
    {"type": "paragraph", "text": "Use agents to widen the first draft, then review with human judgment."}
  ]}}},
  {"command": "slide_add", "args": {"layout": "closing"}},

  {"command": "slot_set", "args": {"slide": 0, "slot": "title", "text": "AI Agents for Product Teams"}},
  {"command": "slot_clear", "args": {"slide": 0, "slot": "subtitle"}},

  {"command": "slot_set", "args": {"slide": 4, "slot": "body", "text": "Start with one workflow, measure quality and speed, then expand."}}
]
JSON
```

Batch payload rules:

- The stdin payload must be a JSON array.
- Each item must be `{"command": "...", "args": {...}}`.
- Use supported mutation commands only: `slide_add`, `slide_remove`, `slide_set_layout`, `slot_set`, `slot_clear`, `slot_bind`.
- `slide_add` can either take an explicit `layout` or an auto-layout payload such as `{"auto_layout": true, "content": {"blocks": [...]}}`.
- If one operation is invalid, the batch fails and the deck write is rolled back. Fix the bad operation and rerun the whole batch.
- `slot_clear` is useful when a layout includes a slot you do not want to keep, for example removing the unused `subtitle` from a title slide.

## Validate and Iterate

Run validation after filling content and again after every meaningful fix:

```bash
agent-slides validate deck.json
```

Treat validation as an editing loop:

1. Read the warning or error code.
2. Fix the content or layout.
3. Run `validate` again.
4. Repeat until the deck is clean enough to build confidently.

Common validation outcomes and what to do:

- `OVERFLOW`: text still overflows at the minimum font size. Shorten the text first. If the idea still needs more space, switch to a roomier layout such as `title_content`, `two_col`, or `comparison`.
- `MAX_WORDS_PER_COLUMN_EXCEEDED`: reduce prose, split the idea across slides, or change to a multi-column layout only if it improves fit.
- `MAX_BULLETS_PER_SLIDE_EXCEEDED`: keep only the essential bullets and move the rest to another slide.
- `FONT_SIZE_OUT_OF_RANGE`: usually a sign the slide is too dense or an override is too aggressive. Remove the override or simplify content.
- `MISSING_TITLE_SLIDE`: make the first slide `title` unless the user intentionally wants a different opening.
- `MISSING_CLOSING_SLIDE`: add a `closing` slide when the deck needs a clear ending.
- Auto-layout picked a valid but weak structure: use `slide set-layout` to correct it, then refill any slots the new layout needs.
- `UNBOUND_NODES`: most often caused by `slide set-layout` when the old layout had slots the new layout does not support. Either move the content into valid slots or choose a layout that matches the content shape better.

If a slide keeps failing validation, do not keep squeezing text. Change the outline.

## Build

Generate the PowerPoint after validation:

```bash
agent-slides build deck.json -o presentation.pptx
```

## Preview

Use preview when you want a live browser view while iterating:

```bash
agent-slides preview deck.json
```

Useful non-browser variant:

```bash
agent-slides preview deck.json --no-open --port 8765
```

## Content Rules of Thumb

- One idea per slide.
- Keep headings short and specific.
- Prefer 3-5 bullets over dense paragraphs.
- Use sentence fragments for bullets.
- For content slides, let `--auto-layout` make the first layout choice before reaching for manual `--layout`.
- Reserve `quote` for one memorable statement, not an entire paragraph.
- Use `comparison` and `three_col` only when each column can stay concise.
- When the topic is broad, split it into multiple `title_content` slides instead of overloading one slide.

## Minimum Deliverable For "Make A Deck About X"

A good default outcome is:

- a 5-slide outline
- a valid `deck.json`
- a built `presentation.pptx`

The shortest reliable sequence is:

```bash
agent-slides init deck.json --theme default --rules default
agent-slides batch deck.json < ops.json
agent-slides validate deck.json
agent-slides build deck.json -o presentation.pptx
```

Where `ops.json` is a single JSON array covering the full slide-add and slot-set sequence for the planned deck.
