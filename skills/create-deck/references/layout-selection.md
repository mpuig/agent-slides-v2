# Layout Selection (Template-Agnostic)

This reference teaches you how to pick layouts for any template.
Read it before Phase 1 (storyline) and Phase 2 (build).

## Step 1: Run inspect

Before planning slides, run `uv run agent-slides inspect <manifest>` to get the full layout catalog with computed constraints. The output includes:

```json
{
  "data": {
    "theme": { "fonts": {...}, "colors": {...} },
    "categories": {
      "full_width_with_body": ["layout_a", "layout_b"],
      "medium_with_body": ["layout_c"],
      "narrow_with_body": ["layout_d"],
      "heading_only": ["layout_e"],
      "image_layouts": ["layout_f"]
    },
    "layouts": [
      {
        "slug": "layout_a",
        "slots": ["heading", "body"],
        "heading_width_pt": 861.0,
        "heading_height_pt": 37.0,
        "width_class": "full",
        "max_heading_words": 12,
        "has_body": true,
        "has_image": false,
        "body_density": "dense",
        "body_max_bullets": 6,
        "heading_text_color": "#333333",
        "bg_color": "#FFFFFF"
      }
    ]
  }
}
```

## Step 2: Understand the categories

The `categories` field groups layouts by their content capacity:

| Category | What it means | Use for |
|----------|--------------|---------|
| `full_width_with_body` | Wide heading + large body area | Dense content slides with 4-6 bullets |
| `medium_with_body` | Medium heading + smaller body | Highlighted insights, 2-3 bullets |
| `narrow_with_body` | Narrow heading + compact body | Short callouts, 1-2 bullets |
| `heading_only` | Heading is the only content | Bold statements, section dividers |
| `image_layouts` | Heading + image slot | Visual slides with photos/graphics |

## Step 3: Use per-layout constraints

Each layout in the `layouts` array tells you exactly what you can do:

### Heading word limits

The `max_heading_words` field is computed from `heading_width_pt`. **Respect it strictly** -- long headings on narrow placeholders will overflow or shrink to unreadable sizes.

| width_class | max_heading_words | Heading style |
|-------------|-------------------|---------------|
| `very_narrow` | 3 | Label: "IoT First" |
| `narrow` | 5 | Short phrase: "Data drives growth" |
| `medium_narrow` | 8 | Brief statement: "Move fast on IoT deployment" |
| `medium` | 10 | Action title: "Revenue grew 12% YoY to EUR 847M" |
| `wide` / `full` | 12 | Full action title with conclusion |

**CRITICAL**: Template heading placeholders are often short (30-40pt tall). Even on full-width layouts, keep headings concise -- 6-10 words is the sweet spot. Put detail in the body, not the heading.

### Body density

The `body_density` and `body_max_bullets` fields tell you how much content fits:

| body_density | body_max_bullets | Content guidance |
|-------------|-----------------|------------------|
| `dense` | 6 | Full body: 4-6 bullets, up to 100 words |
| `medium` | 4 | Moderate: 3-4 bullets, 40-60 words |
| `light` | 3 | Brief: 2-3 short bullets, 20-40 words |
| `minimal` | 2 | Compact: 1-2 very short bullets |

### Background colors

The `bg_color` and `heading_text_color` fields tell you the slide's visual character:
- Light background (white/gray) with dark text: standard content
- Dark/colored background with white text: emphasis, statements, section breaks

Use colored-background layouts for key messages, transitions, and bold statements.
Use light-background layouts for detailed content, data, and analysis.

## Slot rules

### Body slot

- **Set body on every layout that has `has_body: true`.** Empty body slots waste space.
- Body content should support the heading, not repeat it.
- Source lines go FIRST in body: `Source: [attribution]` as the first text block.

### Image slot

- Layouts with `has_image: true` expect a real image file.
- Use relative paths from the deck directory.
- If no image is available, use a different layout.

### Heading-only layouts

- When `has_body: false`, the heading IS the entire message.
- Make it a complete, strong action statement.
- These layouts are for section breaks, bold statements, and emphasis.

## Content-type-to-category mapping

| Content type | Best category | Why |
|-------------|---------------|-----|
| Deck title | First layout with subheading slot | Opener with title + subtitle |
| Dense narrative | `full_width_with_body` | Maximum body area for bullets |
| Key insight | `medium_with_body` | Highlighted takeaway + supporting points |
| Bold statement | `heading_only` (colored bg) | Heading IS the message |
| Section divider | `heading_only` | Structural break |
| Data with source | `full_width_with_body` | Room for data + source line |
| Image + explanation | `image_layouts` | Heading + image |
| Directional callout | `medium_with_body` or `narrow_with_body` | Arrow/directional layouts |
| Closing / CTA | `heading_only` (colored bg) | Compelling final statement |

## Anti-patterns

- **Long headings on narrow layouts.** Check `max_heading_words` and stay within it.
- **Skipping body on layouts that support it.** If `has_body: true`, fill the body.
- **Setting body on heading-only layouts.** If `has_body: false`, do not attempt `slot set --slot body`.
- **Repeating the same layout 3+ times consecutively.** Alternate between categories.
- **Using heading-only layouts for data slides.** Data needs body for bullets and source lines.
- **Ignoring background color variants.** Mix light and colored backgrounds for visual rhythm.

## Layout variety rule

In any deck longer than 6 slides:
- Use at least 3 different layouts.
- Never repeat the same layout for 3+ consecutive content slides.
- Alternate between categories to create visual rhythm.
- Mix light-background and colored-background layouts for contrast.
