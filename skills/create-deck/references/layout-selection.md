# Layout Selection (BCG Template)

This reference is the authoritative catalog of usable BCG template layouts.
Read it before Phase 1 (storyline) and Phase 2 (build) to pick layouts correctly.

## Key Facts

- 24 usable primary layouts (non-d\_ duplicates, non-agenda)
- Most layouts are **heading-only**. Do not attempt to set body on them.
- Heading widths vary from 195pt (very narrow) to 861pt (full width). Word count must match.
- Only 3 layouts have a body slot: `title_slide`, `title_and_text`, `disclaimer`
- Only 2 layouts have an image slot: `green_half`, `green_two_third`

## Complete Layout Catalog

### Opening and Closing

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `title_slide` | heading, subheading, body, image | 541pt | Deck opener. Set heading, subheading, and optionally body. |
| `end` | (none) | -- | Closing slide. No editable slots; use as-is. |

### Full-Width Content (heading w=861pt)

| Slug | Slots | Use For |
|------|-------|---------|
| `title_and_text` | heading, body | Primary content slide. The only non-opener with a body slot. |
| `title_only` | heading | Action title as the entire message. No body. |
| `section_header_line` | heading | Section divider with a line accent. |
| `big_statement_green` | heading | Bold statement on green background. High emphasis. |
| `big_statement_icon` | heading | Bold statement with icon accent. |
| `special_gray` | heading | Statement on gray background. Lower emphasis than green. |

### Medium-Width Layouts (heading w=320-541pt)

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `section_header_box` | heading | 758pt | Section divider with box accent. |
| `green_highlight` | heading | 493pt | Highlighted takeaway on green band. |
| `green_two_third` | heading, image | 492pt | Heading plus image, two-thirds text. |
| `arrow_two_third` | heading | 493pt | Directional takeaway, wide arrow. |
| `green_arrow_two_third` | heading | 493pt | Green directional takeaway, wide arrow. |
| `arrow_half` | heading | 368pt | Directional takeaway, half-width arrow. |
| `green_arrow_half` | heading | 368pt | Green directional takeaway, half-width. |
| `green_half` | heading, image | 346pt | Heading plus image, half-and-half split. |
| `arrow_one_third` | heading | 320pt | Directional takeaway, narrow arrow. |
| `green_arrow_one_third` | heading | 320pt | Green directional takeaway, narrow. |

### Narrow Layouts (heading w=195-272pt)

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `gray_slice_heading` | heading | 272pt | Narrow slice heading. Max ~5 words. |
| `white_one_third` | heading | 246pt | Narrow white panel. Max ~5 words. |
| `green_one_third` | heading | 246pt | Narrow green panel. Max ~5 words. |
| `left_arrow` | heading | 195pt | Very narrow arrow callout. Max ~3 words. |
| `green_left_arrow` | heading | 195pt | Very narrow green arrow. Max ~3 words. |

### Agenda Layouts

These layouts have baked-in template titles (e.g., "Agenda", "Strategy").
Fill the `body` slot ONLY with actual agenda items (numbered topic list
with page references), not titles or descriptions. If the deck has no
real agenda, skip these layouts entirely.

| Slug | Slots | Use For |
|------|-------|---------|
| `agenda_full_width_overview` | body | Full-width agenda with items |
| `agenda_section_header_overview` | body | Section-specific agenda |
| `agenda_two_thirds` | body | Two-thirds width agenda |

### Do Not Use (excluded)

These layouts have baked-in template content or serve no content purpose.
Do NOT include them in decks — they will produce visual artifacts.

| Slug | Reason |
|------|--------|
| `disclaimer` | Template has full legal text baked in; adding body overlaps |
| `layout_guide` | Reference/guide layout, not for presentations |
| `blank` | No fillable slots |
| `blank_green` | No fillable content area |
| `end` | Pre-designed closing graphic; use as-is with no content |

## Quick Slot Lookup

| Slot | Available On |
|------|-------------|
| heading | All layouts except `blank`, `end`, `disclaimer`, `layout_guide` |
| subheading | `title_slide` only |
| body | `title_slide`, `title_and_text`, `disclaimer`, `layout_guide` |
| image | `title_slide`, `green_half`, `green_two_third` |

## Width Classes and Word Limits

| Width Class | Points | Max Words in Heading | Layouts |
|-------------|--------|---------------------|---------|
| Very narrow | 195pt | 3 words | `left_arrow`, `green_left_arrow` |
| Narrow | 246-272pt | 5 words | `white_one_third`, `green_one_third`, `gray_slice_heading` |
| Medium-narrow | 320-368pt | 8 words | `arrow_one_third`, `green_arrow_one_third`, `arrow_half`, `green_arrow_half`, `green_half` |
| Medium | 493-541pt | 12 words | `green_highlight`, `arrow_two_third`, `green_arrow_two_third`, `green_two_third`, `title_slide` |
| Wide | 758pt | 18 words | `section_header_box` |
| Full | 861pt | 20+ words | `title_only`, `title_and_text`, `section_header_line`, `big_statement_green`, `big_statement_icon`, `special_gray` |

## Content-Type-to-Layout Mapping

| Content Type | Best Layout | Why |
|-------------|-------------|-----|
| Deck title with subtitle | `title_slide` | Has heading + subheading + body + image slots |
| Single narrative with body text | `title_and_text` | Only content layout with both heading and body |
| Action title as entire message | `title_only` | Full-width heading, no body distraction |
| Bold key takeaway | `big_statement_green` or `big_statement_icon` | Full-width, high-contrast emphasis |
| Section divider | `section_header_box` or `section_header_line` | Designed as structural breaks |
| Data slide with chart heading | `title_only` | Heading states the insight; chart is a separate element |
| Image with explanation | `green_half` or `green_two_third` | Only layouts with heading + image |
| Directional callout / arrow | `arrow_half` or `green_arrow_half` | Arrow shape implies direction/momentum |
| Short label or tag | `left_arrow` or `green_left_arrow` | Very narrow, for 2-3 word labels |
| Agenda overview | `agenda_full_width_overview` | Body slot for numbered topic list |
| Closing | `big_statement_green` | Use as final call-to-action with heading |

## Anti-Patterns

- **Setting body on heading-only layouts.** 20 of 24 layouts have no body slot. `slot set` on body will fail silently or be ignored.
- **Long headings on narrow layouts.** A 15-word heading on `left_arrow` (195pt) will overflow or become unreadable.
- **Using `title_and_text` for everything.** It is the only layout with body, but overusing it makes the deck monotonous. Use heading-only layouts for variety.
- **Repeating the same layout 3+ times consecutively.** Breaks visual rhythm. Alternate between layout categories.
- **Ignoring the green/white variants.** Green variants add visual weight and color. Alternate them to create contrast.
- **Using arrow layouts for non-directional content.** Arrow shapes imply momentum, transition, or direction. Do not use them for static facts.
- **Adding content to disclaimer/layout_guide/blank layouts.** These have baked-in template content or no content areas. Adding text creates visual artifacts.
- **Adding titles to agenda layouts.** Agenda layouts have their own template titles. Fill body with agenda items only, not headings.

## Layout Variety Rule

In any deck longer than 6 slides, use at least 3 different layouts.
Never repeat the same layout for 3 or more consecutive content slides.
Alternate between full-width, medium, and narrow layouts to create visual rhythm.
Mix green and white variants to maintain color contrast.
