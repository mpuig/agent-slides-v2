# Computed Layout Persistence

Decision date: 2026-03-28

Decision: persist derived layout data in `deck.computed.json`, not in `deck.json`.

## Evaluation

### Option A: Separate `deck.computed.json`

- Pros:
  - Keeps `deck.json` as the source-of-truth model, which removes diff noise and revision churn from derived positions and resolved styles.
  - Gives Milestone 0.3 preview a clean watch boundary: it can watch `deck.computed.json` for "reflow finished" events and then read both files at matching revisions.
  - Preserves the current architecture where preview can consume computed data without embedding the reflow engine.
- Cons:
  - Writing two files is not transactionally atomic across the filesystem.
  - The I/O layer has to manage a second schema and stale-cache handling.

Mitigation:

- The engine writes `deck.json` first and `deck.computed.json` second. Preview should watch the computed sidecar, because its update is the signal that the source deck write has already completed.
- `read_deck()` ignores a computed sidecar whose `deck_id` or `revision` does not match the source deck, so stale cache never becomes source-of-truth.

### Option B: Keep computed in `deck.json`

- Pros:
  - One file, simpler persistence.
  - No coordination between source and cache files.
- Cons:
  - Derived state keeps polluting source diffs.
  - Preview would need field-level change filtering inside a mixed source/cache document.
  - Keeps conceptual ownership muddy right before the first external consumer of computed data ships.

### Option C: Compute on demand only

- Pros:
  - Eliminates cache persistence and staleness entirely.
  - Only one persisted file remains.
- Cons:
  - Forces the preview server to depend on and execute the reflow engine.
  - Adds latency to preview updates and couples Milestone 0.3 preview architecture to engine internals earlier than planned.
  - Makes preview less of a thin consumer and more of a second execution environment.

## Outcome

Option A is the best fit for the approved v0 architecture. It preserves the "sidecar JSON is source of truth" rule for authoring data, keeps computed data available to the preview server as a persisted cache, and gives the preview milestone a cleaner file-watching model without forcing on-demand engine execution.
