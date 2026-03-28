# Common Mistakes

Use this reference during Phase 3 QA.

## Storytelling mistakes

- Topic titles instead of action titles
- Body content that does not prove the title
- Background slides that never reach a recommendation
- Multiple messages fighting on the same slide
- Evidence presented without an explicit conclusion

## Content mistakes

- Paragraph-heavy slides
- Too many bullets
- Unsourced numbers, quotes, or external visuals
- Charts with no clear reason to exist
- Repeating the same point on multiple slides

## Layout mistakes

- Reusing the same layout so often that the deck becomes visually flat
- Choosing a comparison layout for non-comparative content
- Overstuffing `three_col` with too much copy
- Leaving placeholder or orphaned content after layout changes

## Final QA checklist

- Every content slide has an action title.
- Every slide body proves its title.
- Every fact, number, chart, and external image has a source.
- The storyline follows answer -> arguments -> evidence.
- The opener frames the topic clearly.
- The closer states the implication, recommendation, or next action.
- `uv run agent-slides validate deck.json` is clean or the remaining warnings are consciously resolved.
