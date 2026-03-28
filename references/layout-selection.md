# Layout Selection

Choose layouts by the relationship you need the audience to see, not by the raw item count.

## The Isomorphism Principle

The visual structure should mirror the conceptual structure.

If the content presents equal peers, use equal visual weight. If it presents contrast, use side-by-side contrast. If it presents a single narrative, keep the reading path linear. If it presents a visual artifact plus explanation, split the slide into image and narrative zones.

This is the core rule:

- equal ideas should look equal
- contrasted ideas should sit in tension
- hierarchy should look hierarchical
- sequence should look sequential
- emphasis should claim the center or the full frame

Examples:

- Three equally important themes should use `three_col`, because three equal columns signal equal weight.
- Two alternative strategies with distinct labels should use `comparison`, because headers plus paired bodies make the contrast explicit.
- One claim with supporting detail should use `title_content`, because a full-width reading path reinforces a single narrative.
- A single image with explanation should use `image_left` or `image_right`, because the split composition tells the viewer to connect the visual and the text.

Anti-example:

- If one item clearly matters more than the others, do not force it into `two_col` or `three_col`. Equal columns falsely imply equal importance.

## Layout Selection Table

| If the content shows... | Use Layout | Why | Current auto-layout behavior |
| --- | --- | --- | --- |
| Opening/title, talk name, or section opener with a short subtitle | `title` | Centered heading and subtitle create a simple opening beat. | Suggested when content is one heading plus one short paragraph. |
| Single narrative with detail, explanation, or a short bullet list | `title_content` | Full width supports linear reading and one dominant idea. | Suggested for one heading plus one longer paragraph, short bullet lists, and generic text fallback. |
| Two equal pillars, themes, or balanced options | `two_col` | Side-by-side columns signal equal weight and invite comparison. | Suggested for one heading plus two balanced paragraphs, or long bullet lists split for scanning. |
| Three equal pillars, themes, or balanced lenses | `three_col` | Three equal columns make peer relationships explicit. | Suggested for one heading plus three balanced paragraphs. |
| Two contrasted approaches with their own headers and bodies | `comparison` | Header-body pairs create structured contrast instead of generic columns. | Suggested when the content forms two headed groups after a lead heading. |
| Key quote or statement with attribution | `quote` | Centered treatment turns the slide into emphasis, not explanation. | Not auto-suggested; choose it deliberately when emphasis matters more than structure. |
| Image plus explanation, with the image leading the read | `image_left` | Split layout connects the visual to the narrative while letting the image anchor the slide. | Suggested for `image_count == 1` with non-empty text content. |
| Image plus explanation, with the text leading the read | `image_right` | Same relationship as `image_left`, but mirrored for reading flow or composition. | Not auto-suggested directly; today the engine picks `image_left` for the split image-text pattern. |
| Full-impact visual, poster frame, or immersive scene | `hero_image` | Full-bleed image tells the viewer the visual is the message. | Suggested for `image_count == 1` with empty text content. |
| Multiple images, references, or a collection | `gallery` | A grid reads as a set of related visual items. | Suggested for `image_count >= 2` with non-empty text content. |
| Section break, closing thought, or deliberate pause in the narrative | `closing` | Minimal content creates a stop, transition, or ending beat. | Not auto-suggested; validator guidance separately recommends ending decks with a closing slide. |
| Nothing yet, placeholder slide, or intentional empty canvas | `blank` | A clean slate avoids implying structure that does not exist yet. | Suggested when the structured content is empty. |

## Anti-Patterns

- Do not use equal columns for unequal items. Size and span should reflect importance.
- Do not use grids for hierarchies. A grid implies peers, not parent-child structure.
- Do not imply a flow or process for content that is not sequential.
- Do not stack truly equal peers vertically if the main point is parity rather than order.
- Do not repeat the same layout for 3 or more consecutive content slides unless repetition is itself the message.

## Layout Variety Rule

In any deck longer than 6 slides, use at least 2 to 3 different layouts.

Never repeat the same layout for 3 or more consecutive slides. Variety preserves attention and helps each idea feel intentionally framed. The point is not novelty for its own sake; the point is to keep the deck visually aligned with changing relationships from slide to slide.

## Integration with Auto-Layout

`suggest-layout` and `slide add --auto-layout` already implement part of this principle in `src/agent_slides/engine/layout_suggest.py`.

The current engine maps relationship cues to layout choices like this:

- balanced 2-way content becomes `two_col`
- balanced 3-way content becomes `three_col`
- two headed groups become `comparison`
- one heading plus one short paragraph becomes `title`
- one heading plus one longer paragraph becomes `title_content`
- one image plus text becomes `image_left`
- one image without text becomes `hero_image`
- multiple images plus text become `gallery`
- empty content becomes `blank`

That means the engine already applies isomorphism for common patterns: equality, contrast, title/subtitle openings, image-plus-narrative, image-only immersion, and empty-state slides.

Current intentional limits:

- `quote` and `closing` are excluded from auto-suggestion, so agents should select them deliberately when emphasis or pacing matters more than content shape.
- `image_right` is the mirrored manual variant of the split image-text relationship. The current auto-layout engine suggests `image_left`, and authors can flip to `image_right` when the composition reads better that way.
- The variety rule is design guidance, not an enforced validator or `suggest-layout` rule today.

Use the engine as the default heuristic, then override it when the conceptual relationship, reading flow, or deck rhythm calls for a different layout.
