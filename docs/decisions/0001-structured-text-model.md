# Structured Text Model For Slot Content

## Status

Accepted on 2026-03-28 for issue `mpuig/agent-slides-v2#39`.

## Context

`Node.content` previously stored a raw string. That made the engine blind to the semantic structure inside a slot, which blocked three milestone-0.4 requirements:

- design-rule enforcement could only approximate bullet counts by counting non-empty lines,
- text fitting could not model heading-vs-body hierarchy inside the same slot,
- agents could only replace opaque text blobs instead of targeting headings or bullet items.

## Options Evaluated

### A. Structured content model

Canonical shape:

```python
class TextBlock(BaseModel):
    type: Literal["paragraph", "bullet", "heading"]
    text: str
    level: int = 0

class NodeContent(BaseModel):
    blocks: list[TextBlock]
```

Tradeoffs:

- Agent ergonomics: best. Agents can address semantic units directly and batch mutations can submit structured `content`.
- Text fitting: best. The fitter can account for heading scale, block spacing, and bullet indentation.
- Validation: best. Bullet counts and word counts can operate on explicit blocks instead of heuristics.
- PPTX rendering: best. Blocks map naturally to paragraphs, bullet levels, and per-block font sizing.
- Backward compatibility: moderate. Existing string payloads need coercion, but that can be handled at load time.

### B. Markdown-like content string

Tradeoffs:

- Agent ergonomics: mixed. Better than opaque strings, but agents still have to emit syntax instead of data.
- Text fitting: moderate. The renderer still needs a parse step before every consumer can reason about structure.
- Validation: moderate. Works only when authors follow conventions perfectly.
- PPTX rendering: moderate. Viable, but parsing becomes part of the hot path everywhere.
- Backward compatibility: good. Existing strings still load, but ambiguous strings remain ambiguous.

### C. Keep raw strings and improve heuristics

Tradeoffs:

- Agent ergonomics: poor. Still no addressable semantic units.
- Text fitting: poor. No reliable way to apply different sizing rules inside one slot.
- Validation: poor. Heuristics can improve but will still misclassify paragraphs as bullets.
- PPTX rendering: poor. Writer still cannot distinguish bullets from paragraphs reliably.
- Backward compatibility: best short-term, but preserves the core limitation.

## Decision

Choose option A: make structured text the canonical model.

Reasons:

- It is the only option that removes ambiguity instead of moving it around.
- It unlocks milestone-0.4 design-rule enforcement directly.
- It improves both agent mutation semantics and PPTX output without inventing a second parse layer.

## Implementation Notes

- `Node.content` is now `NodeContent`.
- The deck sidecar schema version is bumped from `1` to `2`.
- Legacy string payloads are still accepted on read and coerced into a single paragraph block.
- `slot_set` still accepts raw `text` for CLI ergonomics, and batch mutations may now also send structured `content`.
- Text fitting now estimates height using block types, heading scale, spacing, and bullet indentation.
- PPTX writing renders blocks as separate paragraphs and preserves bullet nesting levels.

## Consequences

- Newly written sidecars emit structured content objects.
- Old sidecars remain readable, but legacy strings are preserved as paragraph blocks rather than guessed into bullets.
- Future commands can add higher-level operations such as `add_bullet`, `replace_heading`, or block-aware editing without changing the storage model again.
