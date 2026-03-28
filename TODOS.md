# TODOS

## Evaluate: Separate computed positions from deck.json
**Priority**: Before Milestone 0.3 (preview server)
**What**: Move `computed` field from `deck.json` to a separate `deck.computed.json` file.
**Why**: `computed` is derived state. Persisting it in the source-of-truth file causes diff noise, potential staleness bugs, and conceptual mudiness. The preview server (0.3) is the first external consumer of computed data — evaluate before it ships.
**Pros**: Cleaner source file diffs, no cache invalidation in source of truth, clearer ownership boundary.
**Cons**: Two files to manage atomically, preview server watches two files, slightly more complex IO layer.
**Context**: Flagged by Codex outside voice as P1 during eng review (2026-03-28). Current design puts computed in sidecar so preview can read without running engine. Alternative: preview calls engine, or reads separate cache file.
**Depends on**: Milestone 0.1 IO layer stabilization. Must be decided before Milestone 0.3 preview server design.

## Design: Structured text model for slots
**Priority**: Post-v0
**What**: Replace raw text strings in slot content with a structured model (paragraphs, bullet items, headings).
**Why**: Design rules reference "max 6 bullets per slide" and "visual hierarchy" but v0 treats all content as opaque strings. Without knowing what a bullet is, these rules can't be enforced programmatically. Also enables richer text fitting (different sizing for headings vs bullets within a slot).
**Pros**: Real content-aware design rules, smarter text fitting per content type, richer agent semantics ("add a bullet to col1" vs "replace all text in col1").
**Cons**: Significant complexity. Changes Node.content from string to structured object. Impacts sidecar schema, text fitting, PPTX writer, and preview renderer. Breaking change to the sidecar format.
**Context**: Flagged by Codex outside voice as P2 during eng review (2026-03-28). v0 works fine with raw strings for the demo target. This becomes important when design rules get serious (Milestone 0.4+).
**Depends on**: Core model stabilization (Milestone 0.2+). Should be designed before Milestone 0.4 (design rules polish).
