# Common Presentation Mistakes

Universal presentation anti-patterns, ranked by severity and written as a QA checklist for `agent-slides` decks. Use this during deck review and during validator/QA rule design.

## How to use this reference

- Read the slide title and body in under 5 seconds. If the takeaway is still fuzzy, the slide is not ready.
- Check whether the current `agent-slides` validator already catches the issue. If it does not, treat this document as the manual QA backstop.
- Prefer layout, structure, and evidence fixes over cosmetic cleanup.

## Critical

These mistakes destroy credibility because the audience cannot trust the argument, the evidence, or the slide logic.

### 1. Topic title instead of action title

**What it looks like**
Bad example: `Q4 Performance`

**Why it's wrong**
Topic titles describe the subject, not the conclusion. The audience must do the synthesis work that the slide should already have done.

**How to fix it**
Rewrite the title as a claim the body can prove.
Better example: `Q4 margin expanded 4 points despite flat volume`

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 2. Too much text on one slide

**What it looks like**
Bad example: a single body area packed with long paragraphs or more than roughly 50 words in one column, so the audience cannot find the point in 5 seconds.

**Why it's wrong**
Dense copy hides the takeaway, reduces scan speed, and usually signals that the writer has not decided what matters.

**How to fix it**
Split the content across slides, convert prose into structured blocks, or move detail into speaker notes or an appendix.

**Which agent-slides validate rule catches it**
`MAX_WORDS_PER_COLUMN_EXCEEDED` in [src/agent_slides/engine/validator.py](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/engine/validator.py) using `content_limits.max_words_per_column` from [src/agent_slides/config/design_rules/default.yaml](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/config/design_rules/default.yaml).

### 3. Body does not prove the title

**What it looks like**
Bad example: title says `Expansion into Spain is the fastest path to growth`, but the slide body only lists market facts without comparing alternatives or showing growth impact.

**Why it's wrong**
A title is a promise. If the evidence does not directly support it, the audience stops trusting the rest of the deck.

**How to fix it**
Either change the title to match the evidence or rebuild the body so every chart, number, and caption advances the stated claim.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 4. Missing source lines for data

**What it looks like**
Bad example: chart or table with specific numbers and no source note, date, or methodology cue.

**Why it's wrong**
Unsourced data looks invented, outdated, or selectively chosen. Credibility drops immediately when the audience cannot inspect provenance.

**How to fix it**
Add a short source line with publisher, dataset or report name, and date. If the number is internal, label it clearly as internal analysis.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 5. Layout does not match the relationship

**What it looks like**
Bad example: a sequential process shown as unrelated bullets, or a comparison shown in a single paragraph instead of side-by-side structure.

**Why it's wrong**
The layout should mirror the underlying logic. When form and meaning disagree, the audience has to mentally re-encode the slide before understanding it.

**How to fix it**
Choose a layout that reflects the relationship: comparison, sequence, hierarchy, grouping, or full-bleed evidence. Use structured slots instead of forcing every message into a generic body box.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only. Related layout guidance exists in [docs/auto-layout.md](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/docs/auto-layout.md).

### 6. Setting body on heading-only layouts

**What it looks like**
Bad example: using `slot set` to put body text on a layout like `big_statement_green` or `arrow_half` which only has a heading slot.

**Why it's wrong**
20 of 24 BCG template layouts have no body slot. Body content set on these layouts is silently dropped, resulting in incomplete slides that look unfinished.

**How to fix it**
Check the layout catalog in `layout-selection.md` before setting slots. If you need both heading and body, use `title_and_text` (the only content layout with both). Otherwise, write the heading as a complete, self-contained action title.

**Which agent-slides validate rule catches it**
`UNBOUND_NODES` may catch some cases, but the real fix is choosing the right layout upfront.

### 7. Missing source attribution

**What it looks like**
Bad example: a slide citing "$4.2B market opportunity" or "32% CAGR" with no source line.

**Why it's wrong**
Unsourced numbers destroy credibility in consulting decks. Every data claim needs provenance.

**How to fix it**
Add "Source: [publisher], [report/dataset], [year]" in the body slot (for `title_and_text`) or as a trailing line in the heading. For internal data, use "Source: Internal analysis" or "Source: Company data, [year]".

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 8. Long headings on narrow layouts

**What it looks like**
Bad example: "Digital transformation is reshaping the competitive landscape across all segments" on a `left_arrow` layout (195pt wide).

**Why it's wrong**
Narrow layouts (195-272pt) can hold at most 3-5 words. Longer headings overflow, get shrunk to unreadable sizes, or break the visual design.

**How to fix it**
Match word count to width class: 3 words for very narrow (195pt), 5 words for narrow (246-272pt), 8 words for medium-narrow (320-368pt). If the message needs more words, pick a wider layout.

**Which agent-slides validate rule catches it**
`OVERFLOW` may catch the worst cases after shrink-to-fit. Prevention is better: consult the width table in `layout-selection.md`.

### 9. Evidence is unreadable even after shrink-to-fit

**What it looks like**
Bad example: text box still overflows or ends up at tiny text size because too much content was forced into the slot.

**Why it's wrong**
If the engine has already shrunk the text to the minimum and it still does not fit, the slide is not recoverable by formatting tweaks.

**How to fix it**
Reduce copy, split the content, or switch to a layout with more space for the content type.

**Which agent-slides validate rule catches it**
`OVERFLOW` in [src/agent_slides/engine/validator.py](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/engine/validator.py), enforced when overflow remains at `overflow_policy.min_font_size`.

## Layout & Structure

These mistakes make the deck look unprofessional even when the underlying idea is sound.

### 10. No visual hierarchy

**What it looks like**
Bad example: title, headers, captions, and body copy all appear at nearly the same size and weight.

**Why it's wrong**
Without hierarchy, the audience does not know where to start. Attention scatters across the slide instead of flowing through the argument.

**How to fix it**
Make the title dominant, use smaller subheads, and keep body text materially smaller than headings. Preserve one clear reading order.

**Which agent-slides validate rule catches it**
`FONT_SIZE_OUT_OF_RANGE` can catch some hierarchy failures when computed heading or body text falls outside configured ranges in [src/agent_slides/config/design_rules/default.yaml](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/config/design_rules/default.yaml). It does not fully validate visual hierarchy.

### 11. Slide has no visual element

**What it looks like**
Bad example: a full slide made only of text blocks, with no chart, table, icon, diagram, or supporting shape structure.

**Why it's wrong**
Text-only slides feel unfinished and force the audience to work too hard. A visual anchor improves scan speed and memory.

**How to fix it**
Add a chart, table, icon-supported callout, process diagram, comparison grid, or simple shape structure that reinforces the message.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 12. Bullet-heavy slide

**What it looks like**
Bad example: seven or more bullets stacked in one body slot.

**Why it's wrong**
Long bullet lists flatten priority and invite the presenter to read the slide verbatim. They usually hide a missing structure decision.

**How to fix it**
Reduce to the few points that matter, group content into columns or sections, or replace bullets with a table, comparison, or process layout.

**Which agent-slides validate rule catches it**
`MAX_BULLETS_PER_SLIDE_EXCEEDED` in [src/agent_slides/engine/validator.py](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/engine/validator.py) using `content_limits.max_bullets_per_slide` from [src/agent_slides/config/design_rules/default.yaml](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/config/design_rules/default.yaml).

### 13. Centered body text

**What it looks like**
Bad example: paragraph or bullet text centered in the middle of a content slide.

**Why it's wrong**
Centered body text is harder to scan, harder to compare line by line, and usually makes dense content feel even denser.

**How to fix it**
Left-align body text. Reserve centering for sparse title slides, section dividers, or intentional hero moments.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 14. Crammed content with no breathing room

**What it looks like**
Bad example: every part of the canvas is occupied, with text or shapes pressed against each other and against slide edges.

**Why it's wrong**
Crowding makes the slide feel anxious and unfinished. It also reduces contrast between major and minor ideas.

**How to fix it**
Delete lower-value content first, then increase whitespace between title, sections, and edges. If necessary, move detail to another slide.

**Which agent-slides validate rule catches it**
No current validator rule. `OVERFLOW` may catch the worst cases, but whitespace quality is mostly manual QA today.

### 15. Action title exceeds two lines

**What it looks like**
Bad example: a title that wraps across three or more lines because it tries to contain the whole paragraph-length story.

**Why it's wrong**
Long titles lose punch, slow down the opening read, and often signal that the writer is combining multiple claims into one slide.

**How to fix it**
Compress to one strong claim with the fewest necessary words. If two ideas remain, split the slide.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 16. Unbound or floating content

**What it looks like**
Bad example: nodes placed on the slide without meaningful slot bindings, making their role in the layout ambiguous.

**Why it's wrong**
Floating content breaks layout semantics and makes the slide harder to maintain, reflow, or validate consistently.

**How to fix it**
Bind each node to the intended slot role and keep content semantic instead of manually positioned.

**Which agent-slides validate rule catches it**
`UNBOUND_NODES` in [src/agent_slides/engine/validator.py](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_127/src/agent_slides/engine/validator.py).

## Formatting

These mistakes look like detail problems, but they still signal weak discipline.

### 17. Animations or slide transitions

**What it looks like**
Bad example: text flying in, chart wipes, or decorative slide transitions between ordinary content slides.

**Why it's wrong**
Animations rarely improve understanding in professional decks. They usually slow the pacing and make the presentation feel less serious.

**How to fix it**
Use static builds. If sequence matters, show it through slide order or an explicit process visual.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 18. Mixing section divider styles

**What it looks like**
Bad example: one divider slide is centered on a dark background, the next uses a photo, and a third looks like a normal content slide.

**Why it's wrong**
Inconsistent divider treatment makes the deck feel assembled from unrelated fragments instead of authored as one narrative.

**How to fix it**
Pick one divider pattern and repeat it consistently across the deck.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 19. Oversized containers with dead space

**What it looks like**
Bad example: a large shaded box or table cell holding only one short line, with most of the area empty.

**Why it's wrong**
Dead space inside containers implies poor sizing discipline and weakens the visual rhythm of the slide.

**How to fix it**
Shrink the container to fit the content, or use the freed space for a more useful visual or cleaner margin.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

### 20. Dense bullet wall without spacing

**What it looks like**
Bad example: bullet list with minimal paragraph spacing, no grouping, and no distinction between primary and secondary points.

**Why it's wrong**
Even when the bullet count is technically acceptable, poor spacing turns the list into a wall of text.

**How to fix it**
Add grouping, reduce the list, or convert it into sections with clear spacing and subheads.

**Which agent-slides validate rule catches it**
`MAX_BULLETS_PER_SLIDE_EXCEEDED` can catch the worst cases, but spacing quality is not directly validated. Manual QA still required.

### 21. Inconsistent number formats, units, or scales

**What it looks like**
Bad example: one chart shows revenue in millions, another in raw currency, and a table mixes percentages with basis points without clear labels.

**Why it's wrong**
Inconsistent numeric framing causes interpretation errors and makes comparisons feel unreliable.

**How to fix it**
Normalize units, label scales explicitly, and use one formatting convention per concept across the deck.

**Which agent-slides validate rule catches it**
No current validator rule. Manual QA only.

## QA checklist

- Does every slide title state a conclusion, not just a topic?
- Can the audience understand the takeaway in 5 seconds?
- Does the body directly prove the title?
- Is every factual chart or table sourced?
- Does the chosen layout match the relationship being explained?
- Is hierarchy obvious from title to body?
- Does each slide include an intentional visual element?
- Are bullets limited, grouped, and well-spaced?
- Is body copy left-aligned and readable?
- Does the slide have enough whitespace to breathe?
- Are divider styles, numeric formats, and evidence labels consistent?
- Are any issues already surfaced by `agent-slides validate`, and are the remaining gaps covered by manual QA?

## Current validator rule map

- `MAX_WORDS_PER_COLUMN_EXCEEDED`: too much text in one slot
- `MAX_BULLETS_PER_SLIDE_EXCEEDED`: bullet-heavy slides
- `FONT_SIZE_OUT_OF_RANGE`: some hierarchy violations
- `OVERFLOW`: unreadable overflow at minimum font size
- `UNBOUND_NODES`: content not attached to layout semantics
- `MISSING_TITLE_SLIDE`: deck missing an opening title slide
- `MISSING_CLOSING_SLIDE`: deck missing a closing slide

Everything else in this reference is currently a manual QA standard rather than an enforced validator rule.
