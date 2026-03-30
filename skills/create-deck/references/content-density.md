# Content Density

Use this reference to make content slides feel finished, legible, and consulting-grade before QA. It defines the minimum visual structure and typography discipline that should sit between a strong story and the final anti-pattern sweep.

## 1. Minimum visual structure

Every content slide needs at least one visible organizing device beyond plain text on a blank canvas:

- a structured layout such as `two_col`, `three_col`, `comparison`, or a clearly segmented `title_content` build
- a data visual such as a chart, table, timeline, or labeled process
- a visual accent such as a card, rule, highlight band, quote panel, or image block

Plain text on white is not a finished slide. If the body is all text, add at least one structure layer with 12-20pt internal padding, 16-24pt separation from adjacent content, or a 4-6pt accent rule that helps the eye group the message.

## 2. Visual hierarchy

Use four text tiers consistently:

- heading: 18-22pt, bold or semibold, brand color
- body: 14-16pt, regular weight, dark text
- secondary labels or annotations: 11-14pt, regular or medium weight, neutral gray
- source line: 9-10pt, regular weight, light gray

Keep at least a 4pt size step between adjacent tiers. Headings should be visibly dominant over body text, and body text should remain darker than secondary text so the reading order is obvious in under 5 seconds.

## 3. Content area fill

The meaningful content should occupy at least 60% of the usable slide area and usually no more than 85%. A slide that fills less than 60% usually looks unfinished; a slide that fills more than 85% usually feels cramped.

As a working rule:

- keep outer margins around 36-56pt
- keep major section gaps around 24-36pt
- leave at least 12-18pt between related blocks

If a slide still feels empty after the core message is present, add structure or emphasis before adding more words.

## 4. Callout numbers

For data-heavy slides, use 1-3 callout numbers as anchors. Set the number at 28-36pt bold, with a short label at 11-13pt below or beside it.

Spacing rules:

- keep 8-12pt between the big number and its label
- keep 16-24pt between adjacent callout blocks
- do not use more than 3 large numbers on one slide unless they are arranged as a true table

The callout should summarize the evidence, not duplicate every data point on the slide.

## 5. Card and block patterns

When content is grouped into cards or blocks, make the pattern deliberate:

- use equal widths and equal heights for peer cards
- keep card padding at 12-18pt on all sides
- keep the gap between cards at 12-20pt
- if using an accent bar, make it 4-6pt thick
- keep text inset from card edges; never let copy touch the border

Cards should clarify grouping, comparison, or sequence. Do not use decorative boxes with inconsistent sizing or random padding.

## 6. Bullet limits

Use no more than 6 bullets on a slide. If the list exceeds 6, split it, convert it into columns, cards, or a table, or move detail to another slide.

Within a bullet area:

- keep bullet text at 14-16pt when it is the main body
- keep bullet-to-bullet spacing around 6-10pt
- avoid multi-line bullets unless each line is essential

If the bullets start reading like paragraphs, the slide needs a new structure, not tighter spacing.

## 7. Font size minimums

Do not shrink away a structure problem. Use these minimums:

- main body: 14pt minimum
- narrow boxes, dense comparison cells, or tight labels: 11pt minimum
- chart labels, captions, and source cues: 9pt minimum

Treat anything below 14pt as an exception that must be justified by the layout. If multiple body areas need to drop to 11pt, split the slide or change the layout.

## 8. Alignment and spacing

Keep geometry disciplined so the slide reads as one system:

- align related blocks to the same x origin
- make parallel items share the same top edge and height when they are peers
- left-align body text and labels unless the slide is a deliberate title or quote moment
- keep repeated offsets consistent within 2-4pt, not visually approximate

Use spacing rhythm deliberately:

- 24-36pt between title and first body block
- 12-18pt between a section header and its content
- 16-24pt between peer columns, cards, or chart-plus-text zones

## 9. Source lines

Every data slide needs a source line at the bottom of the slide. Set it in 9-10pt light gray and keep it inside the content margin, typically 12-18pt above the bottom edge.

The source line should include enough provenance to establish trust, such as publisher or team name, dataset or report label, and date. Keep it short, left-aligned, and visually subordinate to the slide message.

Source line rules:

- Every data slide (charts, statistics, market figures) must have "Source: [attribution]" in the body slot.
- CRITICAL: Place the source line as the FIRST text block in the body content, not the last. The scoring system checks whether a node's full text starts with "Source:" — if bullets come before the source line, it will not be detected. Structure the body as: `[{"type":"paragraph","text":"Source: ..."},{"type":"bullet","text":"..."},...]`
- Internal analysis should be labeled "Source: Internal analysis" or "Source: Company data, [year]".
- External data needs publisher, report name, and year at minimum.
- On heading-only layouts (no body slot), there is no place for a source line. If a slide needs a source line, use `title_and_text` instead.
- When the brief requires a minimum number of source lines, plan which slides get them during Phase 1 and ensure those slides use `title_and_text` layout.

## 10. Heading-only layout discipline

Most BCG template layouts expose only a heading slot. Do not attempt to set body content on heading-only layouts -- the slot does not exist and the content will be lost.

Rules for heading-only layouts:

- The heading IS the entire slide message. Write it as a complete, self-contained action title.
- Do not try to cram body-level detail into the heading. If you need supporting text, use `title_and_text` instead.
- For data slides that need both a heading and a source line, prefer `title_and_text` which has a body slot for the source.
- Heading-only layouts work best for: key takeaways, section dividers, bold statements, and directional callouts.

## 11. Narrow layout word limits

Arrow and one-third layouts have heading widths as narrow as 195-272pt. Long text will overflow or become unreadable.

- Very narrow (195pt): `left_arrow`, `green_left_arrow` -- max 3 words
- Narrow (246-272pt): `white_one_third`, `green_one_third`, `gray_slice_heading` -- max 5 words
- Medium-narrow (320-368pt): arrow half variants, `green_half` -- max 8 words

If your message needs more words, choose a wider layout. Do not force long headings into narrow slots.
