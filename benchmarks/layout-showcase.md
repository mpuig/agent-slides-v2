# Layout Showcase Brief

## Template
examples/bcg.pptx

## Images
Pick images from `examples/images/` using `examples/images/index.json` as a catalogue.
Choose images whose tags match the slide topic. Use relative paths from the deck file
(e.g., `../../examples/images/img_strategy_road_fork_aerial.jpg`).

## Brief
Create a showcase deck using EVERY non-duplicate usable layout from the learned template
manifest. Run `uv run agent-slides inspect .artifacts/bcg.manifest.json` to get the full
list — use all layouts that are usable and do NOT have a `d_` prefix.

For each layout, create one slide with content appropriate to the layout's slot structure:

- **heading + body + image** layouts (title_slide, green_half, green_two_third): fill all
  three slots — use a real image from `examples/images/`, an action title, and body content.
- **heading + body** layouts (title_and_text, section headers, arrow variants, etc.): use an
  action title and 4-6 bullet points or structured body with sub-headings.
- **heading only** layouts: use a strong statement or action title. For narrow-placeholder
  layouts (green_left_arrow, green_arrow_half, arrow_half), keep headings to MAX 5 WORDS.
- **agenda** layouts (agenda_full_width_overview, agenda_section_header_overview,
  agenda_two_thirds): fill body with numbered agenda items ONLY. Do NOT add titles — the
  template has baked-in titles.
- **quote** layout: fill body with a real attributed quote.

**Do NOT use these layouts** — they have baked-in template content or no content areas:
`disclaimer`, `layout_guide`, `blank`, `blank_green`, `end` (use as-is with no content
if needed for closing).

Group slides into a coherent narrative about digital transformation in manufacturing:
1. Title and context (title_slide, section headers)
2. Market analysis (content layouts with data)
3. Strategy options (arrow and comparison layouts)
4. Key statements (big_statement, green highlight variants)
5. Implementation (roadmap content, agenda layouts)
6. Closing (big_statement_green as call-to-action)

Target audience: Manufacturing CEO and executive team
Objective: Present a digital transformation roadmap for a mid-size manufacturer
Key recommendation: Invest EUR 8M over 3 years in IoT, AI-driven quality control, and supply chain digitization to achieve 25% cost reduction

## Required content signals
- Use REALISTIC consulting-style content — action titles, data-driven bullets, source lines. Do NOT use meta-titles like "Layout: title_and_text" or "This demonstrates the arrow layout". Write content as if this were a real strategy deck.
- Body content where available should include 4-6 bullets with specifics (numbers, company names, timeframes)
- Image layouts MUST have real images from examples/images/ — pick by matching tags in index.json
- Narrow layouts (green_left_arrow, green_arrow_half, arrow_half) MUST use SHORT headings (max 5 words)
- At least 5 slides should include a source line (e.g., "Source: McKinsey Digital, 2025")
- Quote layouts should have realistic attributed quotes
- Agenda layouts should have structured agenda items

## Expected slide count
25-32

## Layout variety requirement
At least 22 distinct layout types.
