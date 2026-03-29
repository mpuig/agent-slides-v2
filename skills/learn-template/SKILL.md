---
name: learn-template
description: Guide template ingestion end to end: learn a PPTX, inspect and edit the manifest, smoke-test template-backed layouts, then hand off to create-deck.
---

# Learn Template

Use this skill when the user provides a `.pptx` template and wants to make it usable with `agent-slides`.

In this repo, prefer `uv run agent-slides ...` so the checked-out CLI is used.
Treat `uv run agent-slides contract` as the canonical command contract instead of inferring behavior from older docs or wrappers.

## What this skill teaches

- Learned templates are normal JSON manifests. Review them before using them for deck generation.
- Slot names must stay in the current v0 vocabulary: `heading`, `subheading`, `body`, `col1`, `col2`, `image`.
- Not every layout will be usable. Layouts with no typed placeholders are expected to come back as unusable.
- The manifest stores the original template path in `source` and the template digest in `source_hash`. Moving or modifying the PPTX after learning can break or stale the manifest.
- Extracted `theme` data carries the template's colors, fonts, and spacing into template-backed decks.

## Workflow Overview

Run the work in eight steps:

1. Receive template
2. Learn
3. Inspect
4. Review
5. Edit manifest when needed
6. Test with a small deck
7. Confirm the rendered result
8. Hand off to `create-deck`

## 1. Receive template

Start with a concrete PPTX path. Prefer an absolute path or a repo-relative path that will remain stable.

Quick existence check:

```bash
test -f template.pptx
```

If the file is missing, stop and correct the path before doing anything else.

## 2. Learn

Extract the template manifest:

```bash
uv run agent-slides learn template.pptx -o manifest.json
```

Read both stdout and stderr:

- stdout returns the machine summary with `source`, `layouts_found`, and `usable_layouts`
- stderr may contain useful warnings about skipped placeholder types or a template with zero usable layouts

If the command fails with `Template file not found`, the path is wrong.
If stderr warns that the template has `0 usable layouts`, the template is built from arbitrary shapes rather than typed placeholders. That is outside v0 template ingestion; document that Approach B or full template intelligence would be needed.

## 3. Inspect

Summarize the learned manifest:

```bash
uv run agent-slides inspect manifest.json
```

Also inspect the raw JSON before trusting it:

```bash
uv run python -m json.tool manifest.json
```

Present these findings:

- `source`
- `layouts_found`
- `usable_layouts`
- `theme_extracted`
- each layout's `slug`
- whether each layout is `usable`
- each layout's learned `slots`

Treat the `inspect` output as the fast summary and the raw JSON as the source for manual corrections.

## 4. Review

Review every learned layout, not just the first usable one.

For each layout, show:

- layout `name` and `slug`
- `usable`
- learned slot names in `slot_mapping`
- any obvious mismatch between placeholder intent and slot names

In an interactive run, ask whether the slot names make sense.
In an unattended run, make the judgment yourself from placeholder names, placeholder bounds, and layout structure, then record the assumption.

Use these review rules:

- A title placeholder should map to `heading`.
- A subtitle placeholder should map to `subheading`.
- One body placeholder usually maps to `body`.
- Two body placeholders on the same row usually map to `col1` and `col2`.
- A picture placeholder should map to `image`.
- A stacked or narrow secondary text box is often not a true `col2`. If it behaves more like a sidebar, either leave it unmapped or mark the layout unusable.
- Blank layouts are valid even without placeholders, but they are poor smoke-test candidates because they do not prove text placeholder mapping.

Flag ambiguous cases explicitly:

- two body placeholders where one is clearly a sidebar
- three or more body placeholders that do not fit v0 vocabulary
- layouts whose useful content lives in unsupported placeholder types such as chart, media, or table
- layouts where the placeholder names and bounds disagree with the learned slot names

## 5. Edit Manifest When Needed

Edit `manifest.json` directly when the learned slot mapping is wrong or too optimistic.

Safe edits:

- rename slot keys inside `slot_mapping` to the correct v0 names
- remove a misleading slot from `slot_mapping`
- set `"usable": false` on layouts you want the CLI to ignore

Do not invent new slot names outside:

```text
heading, subheading, body, col1, col2, image
```

Do not casually edit these fields:

- `source`
- `source_hash`
- `index`
- `master_index`
- `theme`
- placeholder `bounds`

Those fields come from the learned template and should normally change only by re-running `learn`.

Example manual correction:

```json
{
  "slug": "agenda",
  "usable": true,
  "slot_mapping": {
    "heading": 0,
    "body": 1
  }
}
```

Example of disabling a misleading layout:

```json
{
  "slug": "sidebar_heavy",
  "usable": false,
  "slot_mapping": {
    "heading": 0,
    "col1": 1,
    "col2": 2
  }
}
```

If the template PPTX was modified after learning, `build` will warn that the template changed. Treat that as a stale manifest and re-run:

```bash
uv run agent-slides learn template.pptx -o manifest.json
```

## 6. Test With A Small Deck

Do a smoke test before handing the manifest to `create-deck`.

First initialize a template-backed deck:

```bash
uv run agent-slides init test.json --template manifest.json
```

Then add two slides using usable layouts from the inspected manifest:

```bash
uv run agent-slides slide add test.json --layout <title_or_first_usable>
uv run agent-slides slide add test.json --layout <content_or_second_usable>
```

Populate the slots that actually exist on those layouts.
For a heading/body layout:

```bash
uv run agent-slides slot set test.json --slide 0 --slot heading --text "Template Smoke Test"
uv run agent-slides slot set test.json --slide 0 --slot subheading --text "Verify title styling and subtitle mapping"
uv run agent-slides slot set test.json --slide 1 --slot heading --text "Content Layout Check"
uv run agent-slides slot set test.json --slide 1 --slot body --text "Verify that learned text placeholders map cleanly into the template."
```

For a two-column layout, use:

```bash
uv run agent-slides slot set test.json --slide 1 --slot heading --text "Two-Column Layout Check"
uv run agent-slides slot set test.json --slide 1 --slot col1 --text "Left column content"
uv run agent-slides slot set test.json --slide 1 --slot col2 --text "Right column content"
```

Build the PPTX:

```bash
uv run agent-slides build test.json -o test.pptx
```

If a supposedly usable layout cannot accept the slots you expected, go back to manifest review rather than forcing bad content into the wrong layout.

## 7. Confirm The Rendered Result

Prefer unattended confirmation first:

```bash
uv run agent-slides review test.json
```

Inspect `test.review/report.md` and the rendered slide PNGs to verify that:

- the slide used the intended template layout
- template colors and fonts were preserved
- text landed in the right placeholders
- no obvious clipping or overflow appeared

If the environment can open desktop files, you can also spot-check the built deck directly:

```bash
open test.pptx
```

If `build` warns that the template changed after learning, the manifest is stale. Re-run `learn`, then repeat the smoke test.

## 8. Hand Off To Create Deck

Once the manifest is clean and the smoke test passes, hand off to `create-deck`:

```bash
/create-deck --template manifest.json "make a deck about Q3 strategy"
```

At that point, `create-deck` should pick from the manifest's usable template layouts instead of the built-in layout set.
