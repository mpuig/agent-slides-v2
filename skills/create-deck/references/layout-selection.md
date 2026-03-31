# Layout Selection (BCG Template)

This reference is the authoritative catalog of usable BCG template layouts.
Read it before Phase 1 (storyline) and Phase 2 (build) to pick layouts correctly.

## Key Facts

- 24 usable primary layouts (non-d\_ duplicates, non-agenda)
- 12 layouts have a body slot (native or virtual). Use body on every content slide that supports it.
- Heading widths vary from 195pt (very narrow) to 861pt (full width). Word count must match.
- Native body: `title_slide`, `title_and_text`, `disclaimer`
- Virtual body (free-floating text box below heading): `title_only`, `special_gray`, `green_highlight`, `gray_slice_heading`, `arrow_half`, `green_arrow_half`, `arrow_two_third`, `green_arrow_two_third`
- Virtual content (editable-region chart/table/image slot when available): use `content` on template layouts whose learned manifest exposes a large editable region. In the BCG template this primarily includes `title_only`, `special_gray`, `green_highlight`, `gray_slice_heading`, `arrow_half`, `green_arrow_half`, `arrow_two_third`, and `green_arrow_two_third`.
- No body (heading vertically centered or large placeholder): `big_statement_green`, `big_statement_icon`, `section_header_box`, `section_header_line`, `left_arrow`, `green_left_arrow`, `white_one_third`, `green_one_third`, `arrow_one_third`, `green_arrow_one_third`
- No body (image layouts): `green_half`, `green_two_third` (heading + image only)
- Image slot: `title_slide`, `green_half`, `green_two_third`

## Charts and Tables on Template Layouts

- When a learned template layout exposes a large editable region, target the virtual `content` slot for charts, tables, and large images instead of forcing them into `body`.
- Use `chart add <deck> --slide <n> --slot content --type <chart-type> --data ...` for native PowerPoint charts on template slides.
- Use `table add <deck> --slide <n> --slot content --data ...` for native PowerPoint tables on template slides.
- Keep `body` for narrative bullets and use `content` for data-heavy visuals. If the slide needs axes, multiple series, or more than 3 numeric comparisons, prefer a chart over bullet text.
- Prefer `green_highlight`, `title_only`, `special_gray`, `arrow_two_third`, and `green_arrow_two_third` for charts and tables because they usually have the largest editable regions. Use `gray_slice_heading`, `arrow_half`, and `green_arrow_half` only for compact visuals.

## Complete Layout Catalog

### Opening and Closing

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `title_slide` | heading, subheading, body, image | 541pt | Deck opener. Set heading, subheading, and optionally body. |
| `end` | (none) | -- | Closing slide. No editable slots; use as-is. |

### Full-Width Content (heading w=861pt)

| Slug | Slots | Use For |
|------|-------|---------|
| `title_and_text` | heading, body (native) | Primary content slide with native body placeholder. Best for dense body text (4-6 bullets). |
| `title_only` | heading, body (virtual) | Action title + supporting bullets via virtual body (3-5 bullets). |
| `section_header_line` | heading | Section divider with a line accent. Heading-only -- no body. |
| `big_statement_green` | heading | Bold statement on green background. Heading IS the message -- no body. |
| `big_statement_icon` | heading | Bold statement with icon accent. Heading IS the message -- no body. |
| `special_gray` | heading, body (virtual) | Statement on gray background. Add 2-3 supporting points in virtual body. |

### Medium-Width Layouts (heading w=320-541pt)

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `section_header_box` | heading | 758pt | Section divider with box accent. Heading-only -- no body. |
| `green_highlight` | heading, body (virtual) | 493pt | Highlighted takeaway on green band. Add 2-3 short bullets in body. |
| `green_two_third` | heading, image | 492pt | Heading plus image, two-thirds text. No body. |
| `arrow_two_third` | heading, body (virtual) | 493pt | Directional takeaway, wide arrow. Add 2-3 bullets in body. |
| `green_arrow_two_third` | heading, body (virtual) | 493pt | Green directional takeaway. Add 2-3 bullets in body. |
| `arrow_half` | heading, body (virtual) | 368pt | Directional takeaway, half-width. Add 2 short bullets in body. |
| `green_arrow_half` | heading, body (virtual) | 368pt | Green directional half-width. Add 2 short bullets in body. |
| `green_half` | heading, image | 346pt | Half-and-half image split. No body. |
| `arrow_one_third` | heading | 320pt | Narrow directional takeaway. Heading-only -- no body. |
| `green_arrow_one_third` | heading | 320pt | Narrow green directional. Heading-only -- no body. |

### Narrow Layouts (heading w=195-272pt)

| Slug | Slots | Heading Width | Use For |
|------|-------|--------------|---------|
| `gray_slice_heading` | heading, body (virtual) | 272pt | Narrow slice heading. Max ~5 words. Add 1-2 very short bullets in body. |
| `white_one_third` | heading | 246pt | Narrow white panel. Max ~5 words. Heading-only -- no body. |
| `green_one_third` | heading | 246pt | Narrow green panel. Max ~5 words. Heading-only -- no body. |
| `left_arrow` | heading | 195pt | Very narrow arrow callout. Max ~3 words. Heading-only -- no body. |
| `green_left_arrow` | heading | 195pt | Very narrow green arrow. Max ~3 words. Heading-only -- no body. |

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
| body (native) | `title_slide`, `title_and_text`, `disclaimer`, `layout_guide` |
| body (virtual) | `title_only`, `special_gray`, `green_highlight`, `gray_slice_heading`, `arrow_half`, `green_arrow_half`, `arrow_two_third`, `green_arrow_two_third` |
| content (virtual chart/table/image) | Template layouts with large editable regions, especially `title_only`, `special_gray`, `green_highlight`, `gray_slice_heading`, `arrow_half`, `green_arrow_half`, `arrow_two_third`, `green_arrow_two_third` |
| image | `title_slide`, `green_half`, `green_two_third` |

**Use body on every layout that supports it.** For heading-only layouts (no body), the heading IS the entire message -- make it a strong action title.

## CRITICAL: Heading Placeholder Height

The BCG template heading placeholder is only **37pt tall** (about 1 line at 24pt font). The engine will shrink the font to fit, but long headings still look cramped and may overlap with body content.

**Rule of thumb: keep headings to 6-10 words (40-60 characters) on all layouts.** This ensures readable text at a good font size. Put the detail in the body, not the heading.

Bad: "The EU mid-market SaaS opportunity has reached EUR 48B and is growing at 14% CAGR driven by digital transformation" (18 words, will shrink to tiny font)
Good: "EU SaaS market reached EUR 48B at 14% CAGR" (9 words, fits in 1 line)

## Width Classes and Word Limits

| Width Class | Points | Max Words in Heading | Layouts |
|-------------|--------|---------------------|---------|
| Very narrow | 195pt | 3 words | `left_arrow`, `green_left_arrow` |
| Narrow | 246-272pt | 5 words | `white_one_third`, `green_one_third`, `gray_slice_heading` |
| Medium-narrow | 320-368pt | 8 words | `arrow_one_third`, `green_arrow_one_third`, `arrow_half`, `green_arrow_half`, `green_half` |
| Medium | 493-541pt | 8 words | `green_highlight`, `arrow_two_third`, `green_arrow_two_third`, `green_two_third`, `title_slide` |
| Wide | 758pt | 12 words | `section_header_box` |
| Full | 861pt | 10 words | `title_only`, `title_and_text`, `section_header_line`, `big_statement_green`, `big_statement_icon`, `special_gray` |

## Content-Type-to-Layout Mapping

| Content Type | Best Layout | Why |
|-------------|-------------|-----|
| Deck title with subtitle | `title_slide` | Has heading + subheading + body + image slots |
| Single narrative with body text | `title_and_text` | Native body placeholder, best for dense text (4-6 bullets) |
| Action title + supporting evidence | `title_only` | Full-width heading + virtual body for 3-5 bullets |
| Bold key takeaway | `big_statement_green` or `big_statement_icon` | Full-width, high-contrast emphasis. Heading IS the message (no body). |
| Section divider | `section_header_box` or `section_header_line` | Structural break. Heading-only. |
| Data slide with source | `title_and_text` or `title_only` | Heading states insight; body has source line + bullets |
| Data-heavy chart or table | `green_highlight`, `title_only`, `special_gray`, `arrow_two_third` | Use the virtual `content` slot so the editable region controls chart/table placement |
| Highlighted insight | `green_highlight` | Green band emphasis + virtual body for 2-3 supporting bullets |
| Image with explanation | `green_half` or `green_two_third` | Heading + image (no body). Make heading the full message. |
| Directional callout / arrow | `arrow_half` or `green_arrow_half` | Arrow implies momentum + virtual body for 2 supporting points |
| Short label or tag | `left_arrow` or `green_left_arrow` | Very narrow, 2-3 word heading only. No body. |
| Agenda overview | `agenda_full_width_overview` | Body slot for numbered topic list |
| Closing | `big_statement_green` | Call-to-action heading (no body). Make heading compelling. |

## Anti-Patterns

- **Long headings on narrow layouts.** A 15-word heading on `left_arrow` (195pt) will overflow or become unreadable.
- **Skipping body on layouts that support it.** If a layout has body (native or virtual), fill it with supporting content.
- **Putting charts or tables in `body` when `content` exists.** On template layouts with editable regions, use `content` for charts/tables so they take the full safe zone instead of text-box geometry.
- **Setting body on layouts without it.** `big_statement_green`, `big_statement_icon`, `section_header_box`, `section_header_line`, `left_arrow`, `green_left_arrow`, `white_one_third`, `green_one_third`, `arrow_one_third`, `green_arrow_one_third`, `green_half`, `green_two_third` do NOT have body. Do not attempt `slot set --slot body` on these.
- **Overloading narrow layout bodies.** `gray_slice_heading` body should have at most 1-2 very short bullets.
- **Using `title_and_text` for everything.** With virtual body slots on 8+ layouts, mix layout types for variety.
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
