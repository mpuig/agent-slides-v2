# Auto Layout

`agent-slides` ships a rule-based suggestion engine for choosing a slide layout from structured text content. The same engine also powers `slide add --auto-layout`, which picks the top-ranked layout and pre-fills the text slots on the new slide.

This document describes the current implementation in:

- `src/agent_slides/engine/layout_suggest.py`
- `src/agent_slides/commands/suggest_layout.py`
- `src/agent_slides/commands/slide.py`
- `src/agent_slides/commands/mutations.py`

## `suggest-layout` Command

`suggest-layout` accepts structured `NodeContent` JSON plus an optional `--image-count` hint:

```bash
agent-slides suggest-layout \
  --content '{"blocks":[{"type":"heading","text":"Highlights"},{"type":"bullet","text":"Revenue up"}]}' \
  --image-count 1
```

### Input

- `--content` is required.
- The payload must validate as `NodeContent`.
- The command accepts inline JSON or `@path/to/file.json`.
- The payload must be structured blocks, not a raw string.
- `--image-count` is optional and defaults to `0`.

Relevant `NodeContent` fields for the heuristic are the `blocks` array and each block's `type`, `text`, and `level`.

### Output

The command returns up to 3 ranked suggestions:

```json
{
  "ok": true,
  "data": {
    "suggestions": [
      {
        "layout": "two_col",
        "score": 0.7,
        "reason": "A long bullet list is easier to scan in two columns."
      }
    ]
  }
}
```

Each suggestion contains:

- `layout`: the candidate layout slug
- `score`: the heuristic confidence score
- `reason`: the matched rule explanation

### Ranking Behavior

The engine walks the 12 rules in priority order and keeps only the first match for each layout name.

After rule collection, suggestions are sorted by:

1. descending `score`
2. ascending rule index for tied scores

Two layouts are never auto-suggested, even if they appear in `available_layouts`:

- `quote`
- `closing`

## Suggestion Rules

The rules are evaluated in the order shown below.

| Priority | Layout | Score | Signals | Reason |
| --- | --- | ---: | --- | --- |
| 1 | `gallery` | 0.95 | `image_count >= 2` and content is not empty | Multiple images plus supporting text fit a gallery slide. |
| 2 | `image_left` | 0.90 | `image_count == 1` and content is not empty | A single image with text fits a split image-and-text slide. |
| 3 | `hero_image` | 0.90 | `image_count == 1` and content is empty | A single image without text fits a full-bleed hero slide. |
| 4 | `blank` | 0.80 | `block_count == 0` | Empty content should start from a blank slide. |
| 5 | `title` | 0.90 | exactly 1 heading, exactly 1 remaining block, that block is a paragraph, and its word count is below `short_text_threshold` | A heading with a short subtitle fits the title layout. |
| 6 | `title_content` | 0.85 | exactly 1 heading, exactly 1 remaining block, that block is a paragraph, and its word count is at least `short_text_threshold` | A heading with one paragraph fits a title-and-content slide. |
| 7 | `two_col` | 0.90 | exactly 1 heading, exactly 2 remaining blocks, both paragraphs, and their word counts are balanced within `equal_length_threshold` | Two balanced content blocks fit a two-column layout. |
| 8 | `three_col` | 0.90 | exactly 1 heading, exactly 3 remaining blocks, all paragraphs, and their word counts are balanced within `equal_length_threshold` | Three balanced content blocks fit a three-column layout. |
| 9 | `comparison` | 0.90 | exactly 3 headings total and the remaining blocks split into exactly 2 groups, each starting with a heading | Two headed groups suggest a comparison slide. |
| 10 | `title_content` | 0.80 | exactly 1 heading, at least 1 remaining block, all remaining blocks are bullets, and `4 <= bullet_count <= max_bullets_for_single_column` | A short bullet list still fits a single-column content slide. |
| 11 | `two_col` | 0.70 | exactly 1 heading, at least 1 remaining block, all remaining blocks are bullets, and `bullet_count > max_bullets_for_single_column` | A long bullet list is easier to scan in two columns. |
| 12 | `title_content` | 0.50 | any non-empty text content that did not match a higher-priority rule | Generic text content falls back to the title-and-content layout. |

### Configurable Thresholds

The following thresholds come from `src/agent_slides/config/design_rules/default.yaml` under `layout_hints`:

| Setting | Default | Used By |
| --- | ---: | --- |
| `short_text_threshold` | 10 | Distinguishes `title` from `title_content` for a single paragraph after the heading |
| `equal_length_threshold` | 0.4 | Decides whether 2- or 3-paragraph splits count as balanced columns |
| `max_bullets_for_single_column` | 5 | Decides whether bullet-heavy content stays in `title_content` or moves to `two_col` |

The balance check is:

```text
(max(word_counts) - min(word_counts)) / max(word_counts) <= equal_length_threshold
```

A zero-word block always fails the balance check.

## Content Analysis

The heuristics depend on structured text, not plain strings. `NodeContent` exposes the block sequence directly, which lets the engine inspect semantic signals:

- `block_count`: total number of blocks
- `bullet_count`: number of blocks whose type is `bullet`
- `word_count`: total word count across all blocks
- `heading_count`: number of blocks whose type is `heading`
- `has_text`: `True` when the content is not empty

### Heading-Led Analysis

Several rules assume the first block is the slide heading.

The engine computes:

- `blocks`: the original block list
- `remaining_blocks`: `blocks[1:]` only when the first block is a heading; otherwise `[]`

This means the title, single-paragraph, equal-column, and bullet-list rules only match heading-led content.

### Grouping by Heading Boundaries

For comparison-style detection, the engine groups `remaining_blocks` into sections that restart at each heading:

```text
heading: Platform choices
heading: Build
paragraph: Faster setup
heading: Buy
paragraph: Less control
```

produces:

```text
[
  [heading("Build"), paragraph("Faster setup")],
  [heading("Buy"), paragraph("Less control")]
]
```

The `comparison` rule matches only when:

- there are exactly 3 headings in the full content
- there are exactly 2 grouped sections after the first heading
- both grouped sections start with a heading

### Equal-Length Detection for Columns

`two_col` and `three_col` require:

- a single leading heading
- exactly 2 or 3 remaining blocks
- every remaining block must be a paragraph
- the paragraph word counts must be balanced by the formula above

The check uses word counts only. It does not inspect sentence count, punctuation, or rendered height.

## `slide add --auto-layout`

`slide add --auto-layout` uses the top-ranked suggestion only:

```bash
agent-slides slide add deck.json \
  --auto-layout \
  --content '{"blocks":[{"type":"heading","text":"Highlights"},{"type":"paragraph","text":"Left"},{"type":"paragraph","text":"Right"}]}'
```

### CLI Behavior

- `--auto-layout` and `--layout` are mutually exclusive.
- `--content` is required when `--auto-layout` is set.
- `--content` cannot be used without `--auto-layout`.
- `--image-count` defaults to `0`.
- `--image-count` cannot be used without `--auto-layout`.
- Empty structured content is rejected before suggestion with: `Argument 'content' must include at least one text block`.

The command returns:

- `slide_index`
- `slide_id`
- selected `layout`
- `auto_selected: true`
- a summarized `reason`

The returned `reason` is shortened from the full suggestion message. For example, `Two balanced content blocks fit a two-column layout.` becomes `Two balanced content blocks`.

### Content-to-Slot Assignment

After the winning layout is chosen, the mutation path:

1. creates the slide with one placeholder node per slot
2. removes blocks whose `text.strip()` is empty
3. looks for the first slot whose role is `heading`
4. looks for the first block whose type is `heading`
5. if a heading slot exists:
   - assign the first heading block to that slot
   - if there is no heading block, assign the first non-empty block instead
6. collect all remaining non-image slots in declared slot order, excluding the heading slot
7. chunk the remaining blocks across those slots
8. write one `NodeContent` group per target slot

### Chunking Logic

Chunking is count-based, not semantic:

- if there is 1 target slot, all remaining blocks go into it
- if there are fewer blocks than slots, each block gets its own slot and trailing slots remain placeholders
- otherwise, the blocks are split into near-even groups using `ceil(remaining_blocks / remaining_slots)`

Examples:

- `two_col` with 2 remaining blocks assigns one block to `col1` and one block to `col2`
- `three_col` with 5 remaining blocks assigns groups of `2`, `2`, and `1`

### Image Slots

`--image-count` influences layout choice, but it does not synthesize image content.

If the chosen layout contains image slots such as `image_left`, `gallery`, or `hero_image`:

- the slide is created with placeholder image nodes for those slots
- `_populate_auto_layout_slide()` skips slots whose role is `image`
- only the text slots are filled from `--content`

## Integration with Templates

The suggestion engine itself supports narrowing the candidate set through the `available_layouts` parameter:

```python
suggest_layouts(content, available_layouts=registry.list_layouts())
```

This is the integration point for `TemplateLayoutRegistry`, because `TemplateLayoutRegistry.list_layouts()` returns only usable template layouts.

Current implementation detail:

- the engine supports template-aware filtering
- the shipped `suggest-layout` CLI does not expose `available_layouts`
- the current `slide add --auto-layout` mutation calls the suggester without `available_layouts`

So template integration exists at the engine API boundary today, but it is not yet wired through the public CLI path.
