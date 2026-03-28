---
name: create-deck
description: Orchestrate end-to-end deck creation from a natural-language brief using the agent-slides CLI. Use when asked to make a deck, presentation, or slide outline from a topic, and turn it into a validated deck JSON plus optional PPTX output.
---

# Create Deck

Use this skill when the user gives a topic such as "make a deck about X" and wants a complete presentation built with `agent-slides`.

Keep this skill focused on orchestration. Do not restate or invent design rules here. Design rules live in `config/design_rules/` and are enforced by `agent-slides validate`.

## Quick Workflow

1. Plan a 5-10 slide outline from the brief.
2. Choose a theme and initialize the deck.
3. Add slides with the right built-in layouts.
4. Fill slots, preferably with one `batch` call.
5. Run `validate`, fix warnings, then validate again.
6. Build the `.pptx`.
7. Optionally run `preview`.

If `agent-slides` is not already on `PATH`, run the same commands through the repo wrapper the project uses, for example `uv run agent-slides ...`.

## Plan First

Before touching the CLI, turn the brief into a slide plan:

- Default to 5 slides for a simple topic.
- Use 6-8 slides when the topic needs setup, comparison, and takeaway slides.
- Stay under 10 slides unless the user explicitly asks for more.
- Put one idea on each slide.
- Prefer short headings and concise bullet text.
- Draft the outline before generating commands so slide order, layouts, and slot names are clear.

Good default 5-slide structure:

1. Title slide
2. Problem or context
3. Main points or comparison
4. Proof, quote, or example
5. Closing / takeaway

## Choose Layouts From Content Shape

Use only built-in layouts that exist:

- `title`: title slide with `heading` and `subheading` slots. Aliases `title` and `subtitle` also work for slot setting. If you want a title-only opener, remove the unused subtitle slot with a batch `slot_clear`.
- `title_content`: one heading plus one body area. Best default for explanation, agenda, summary, or bullets.
- `two_col`: one heading plus two body columns. Aliases `left` and `right` also work for slot setting.
- `comparison`: structured comparison with `heading`, `left_header`, `left_body`, `right_header`, `right_body`.
- `three_col`: one heading plus three short columns.
- `quote`: `quote` plus `attribution`.
- `closing`: single `body` slot for final takeaway or call to action.
- `blank`: only when you intentionally need an empty slide.

Layout selection heuristics:

- Intro / cover -> `title`
- Agenda / summary / simple explanation -> `title_content`
- Two competing options / before-vs-after -> `two_col` or `comparison`
- Three pillars / three steps -> `three_col`
- Testimonial / key quote -> `quote`
- Final takeaway / thank-you / CTA -> `closing`

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
agent-slides slide add deck.json --layout title_content
agent-slides slide add deck.json --layout comparison
agent-slides slide add deck.json --layout quote
agent-slides slide add deck.json --layout closing
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
  {"command": "slide_add", "args": {"layout": "title_content"}},
  {"command": "slide_add", "args": {"layout": "two_col"}},
  {"command": "slide_add", "args": {"layout": "title_content"}},
  {"command": "slide_add", "args": {"layout": "closing"}},

  {"command": "slot_set", "args": {"slide": 0, "slot": "title", "text": "AI Agents for Product Teams"}},
  {"command": "slot_clear", "args": {"slide": 0, "slot": "subtitle"}},

  {"command": "slot_set", "args": {"slide": 1, "slot": "heading", "text": "Why teams are experimenting now"}},
  {"command": "slot_set", "args": {"slide": 1, "slot": "body", "text": "- Faster drafting\n- Better repetitive-task coverage\n- Lower cost to test ideas"}},

  {"command": "slot_set", "args": {"slide": 2, "slot": "heading", "text": "Human-only vs agent-assisted"}},
  {"command": "slot_set", "args": {"slide": 2, "slot": "left", "text": "- Strong judgment\n- Slower first pass"}},
  {"command": "slot_set", "args": {"slide": 2, "slot": "right", "text": "- Faster iteration\n- Needs review"}},

  {"command": "slot_set", "args": {"slide": 3, "slot": "heading", "text": "Adoption rule"}},
  {"command": "slot_set", "args": {"slide": 3, "slot": "body", "text": "Use agents to widen the first draft, then review with human judgment."}},

  {"command": "slot_set", "args": {"slide": 4, "slot": "body", "text": "Start with one workflow, measure quality and speed, then expand."}}
]
JSON
```

Batch payload rules:

- The stdin payload must be a JSON array.
- Each item must be `{"command": "...", "args": {...}}`.
- Use supported mutation commands only: `slide_add`, `slide_remove`, `slide_set_layout`, `slot_set`, `slot_clear`, `slot_bind`.
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
