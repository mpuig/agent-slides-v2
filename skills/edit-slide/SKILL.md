---
name: edit-slide
description: Modify an existing agent-slides deck in place. Inspect → smallest mutation → validate. Handles layout switches, slot edits, content changes, rebinding, and batch operations.
---

# Edit Slide

Use this skill to modify an existing `agent-slides` deck in place. Stay operational: inspect the current deck state, make the smallest mutation that satisfies the request, then validate the result. Do not apply design opinions or rewrite content beyond the requested edit.

In this repo, prefer `uv run agent-slides ...` so the command uses the checked-out CLI.
Treat `uv run agent-slides contract` as the canonical command contract instead of inferring semantics from scattered docs or wrappers.

## When to use it

- The deck already exists and the task is to change, add, remove, reorder, or retarget slide content.
- The request is phrased as a natural-language edit such as "change the title", "turn slide 3 into three columns", "remove the closing slide", or "clear the right column".
- The task is iterative deck maintenance, not first-time deck creation.

## Current v0 limits

- Slides can be appended with `slide add` and removed with `slide remove`.
- Slides cannot be inserted at an arbitrary position or reordered by a dedicated command in v0.
- If a request depends on true reordering, do not pretend the CLI supports it. Stay within the available operations.

## Workflow Overview

Run the work in four steps:

1. Inspect
2. Mutate
3. Validate
4. Repair fallout when layout or bindings changed

## Core workflow

1. Inspect first.
   Run `uv run agent-slides info <deck.json>` and locate the target slide by index or `slide_id`.
   Confirm the current `layout`, `slide_id`, node ids, and any existing `slot_binding` values before mutating.
2. Apply the smallest edit that matches the request.
   Prefer single commands for one-off changes.
   Use `batch` when several edits should succeed or fail together.
3. Validate after editing.
   Re-run `uv run agent-slides info <deck.json>` to verify the new slide state.
   Run `uv run agent-slides validate <deck.json>` to catch warnings such as unbound nodes or text overflow.
4. If the edit changed layout or bindings, inspect for fallout.
   `slide set-layout` can leave nodes unbound; handle those explicitly before you stop.

## CLI Surface To Use

Prefer the shipped repo commands rather than inventing alternate entry points:

- `uv run agent-slides info`
- `uv run agent-slides slide add`
- `uv run agent-slides slide remove`
- `uv run agent-slides slide set-layout`
- `uv run agent-slides slot set`
- `uv run agent-slides slot clear`
- `uv run agent-slides slot bind`
- `uv run agent-slides batch`
- `uv run agent-slides validate`

## Commands to reach for

### Inspect deck state

```bash
uv run agent-slides info deck.json
```

Use this to answer:

- Which slide index or `slide_id` should I edit?
- What is the current layout?
- Which node ids exist on the slide?
- Which slots are already populated or unbound?

### Change text content

Use `slot set` to write text into a slot. This updates the existing node for that slot or creates one if the slot is currently empty.

```bash
uv run agent-slides slot set deck.json --slide 1 --slot heading --text "Q2 Pipeline Review"
```

Common aliases also work:

- `title` -> `heading`
- `subtitle` -> `subheading`
- `left` -> `col1`
- `right` -> `col2`

Example:

```bash
uv run agent-slides slot set deck.json --slide s-2 --slot title --text "Launch Plan"
```

### Switch layout

Use `slide set-layout` when the user wants a different slide structure.

```bash
uv run agent-slides slide set-layout deck.json --slide 2 --layout three_col
```

This command writes a success payload to stdout. If any nodes cannot be rebound into the new layout, it also writes a warning JSON payload to stderr with code `UNBOUND_NODES` and the affected `node_id` values.

After any layout switch:

1. Read stdout and stderr.
2. If `unbound_nodes` is empty, continue.
3. If nodes became unbound, inspect the slide with `info`, then either:
   - rebind a node into a valid slot with `slot bind`, or
   - clear/remove content the user no longer wants.
4. Re-run `validate`.

### Add a slide

`slide add` always appends in v0. It does not insert into the middle of the deck.

```bash
uv run agent-slides slide add deck.json --layout title_content
```

The stdout payload returns the new `slide_index`, `slide_id`, and `layout`.

If the user asked for "add a slide after slide 2", append the new slide and then continue editing the deck with that new tail slide. Do not claim the CLI inserted it in place.

### Remove a slide

Remove by index or `slide_id`.

```bash
uv run agent-slides slide remove deck.json --slide 4
```

```bash
uv run agent-slides slide remove deck.json --slide s-5
```

When the request is "remove the last slide", inspect first to confirm the last index:

```bash
uv run agent-slides info deck.json
```

### Clear a slot

Use `slot clear` when content should be removed from a slot entirely.

```bash
uv run agent-slides slot clear deck.json --slide 1 --slot col2
```

This removes any nodes currently bound to that slot on the slide.

### Rebind nodes

Use `slot bind` after layout changes when content still exists but its `slot_binding` is `null`.

1. Find the `node_id` from the `UNBOUND_NODES` warning or from `info`.
2. Bind it to a valid slot on the same slide.

```bash
uv run agent-slides slot bind deck.json --node n-7 --slot col3
```

If the destination slot already has a different bound node, the bind operation keeps the target node and prunes conflicting nodes already bound to that slot. Re-check the slide with `info` after binding.

### Batch edits

Use `batch` when the request is a bundle of related edits and you want one atomic write.

```bash
cat <<'JSON' | uv run agent-slides batch deck.json
[
  {"command": "slot_set", "args": {"slide": "s-2", "slot": "title", "text": "Launch Plan"}},
  {"command": "slot_set", "args": {"slide": "s-2", "slot": "subtitle", "text": "Updated timeline"}},
  {"command": "slide_add", "args": {"layout": "quote"}},
  {"command": "slot_set", "args": {"slide": 3, "slot": "quote", "text": "Move fast, but keep the deck valid."}}
]
JSON
```

Prefer individual commands instead of `batch` when:

- you need to inspect `UNBOUND_NODES` immediately after a layout switch,
- you are still discovering the correct target slide or slot,
- the user asked for one small edit and atomicity does not matter.

## Natural-language edit patterns

### "Change the title"

1. Inspect the deck.

```bash
uv run agent-slides info deck.json
```

2. Update the slot.

```bash
uv run agent-slides slot set deck.json --slide 0 --slot heading --text "New Title"
```

3. Validate.

```bash
uv run agent-slides validate deck.json
```

### "Switch slide 3 to three columns"

1. Inspect the current slide.

```bash
uv run agent-slides info deck.json
```

2. Change the layout.

```bash
uv run agent-slides slide set-layout deck.json --slide 2 --layout three_col
```

3. If stderr reports `UNBOUND_NODES`, inspect and rebind.

```bash
uv run agent-slides slot bind deck.json --node n-9 --slot col3
```

4. Fill the new slot if needed.

```bash
uv run agent-slides slot set deck.json --slide 2 --slot col3 --text "New third column"
```

5. Validate.

```bash
uv run agent-slides validate deck.json
```

### "Add a slide after slide 2"

1. Append the slide.

```bash
uv run agent-slides slide add deck.json --layout title_content
```

2. Inspect the returned `slide_index` or confirm with `info`.
3. Populate the new slide with `slot set`.

### "Remove the last slide"

1. Inspect to confirm the last slide index or `slide_id`.

```bash
uv run agent-slides info deck.json
```

2. Remove it.

```bash
uv run agent-slides slide remove deck.json --slide 4
```

### "Clear the right column"

```bash
uv run agent-slides slot clear deck.json --slide 1 --slot right
```

### "Make these five edits together"

Use `batch` only after you know every slide reference and slot name you need. Build the JSON array first, then apply it atomically.

## Error recovery

### Invalid slot

If a command returns `INVALID_SLOT`, do not guess. Recover by:

1. Checking the slide’s current `layout` in `info`.
2. Reading the error message, which lists the allowed slots for that layout.
3. Retrying with a valid slot name or switching layouts first.

### Invalid slide reference

If a command returns `INVALID_SLIDE`, rerun `info` and target the slide by the correct index or `slide_id`.

### Invalid layout

If `slide add` or `slide set-layout` returns `INVALID_LAYOUT`, retry with a supported layout name.

### Unbound nodes after layout switch

If `slide set-layout` returns `UNBOUND_NODES`:

1. Inspect the slide with `info`.
2. Rebind kept content with `slot bind`.
3. Clear content that should be removed.
4. Re-run `validate` and ensure the slide no longer has unresolved unbound content you care about.

### Batch failure

`batch` fails atomically. If one operation is invalid, none of the edits are written. Use the reported `operation_index` to find the failing entry, fix it, and rerun the whole batch.

## Validation checklist

Before stopping, confirm all of the following:

- `info` shows the intended layout, slide count, node bindings, and text.
- `validate` returns the deck in the expected state.
- Any `UNBOUND_NODES` warning from a layout switch has been handled intentionally.
- The final deck state matches the user’s requested edit and nothing more.
