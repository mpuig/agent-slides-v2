# Demo Research Program

This file is the evolving research policy for the demo quality loop.
It controls what the experiment cycle agent does on each run.

## Current lane

**engine** — fix template placeholder text formatting in the PPTX writer.

## Lane boundaries

### Engine lane (current)
Files the agent MAY edit:
- `src/agent_slides/io/pptx_writer.py`
- `src/agent_slides/io/template_reader.py`
- `src/agent_slides/engine/reflow.py`
- `tests/test_pptx_writer.py`
- `tests/test_learn.py`
- `tests/test_template_reflow.py`
- `tests/test_e2e_template.py`

Files the agent MUST NOT edit:
- `skills/**`
- `benchmarks/**`
- `program-demo.md`
- `src/agent_slides/commands/**`
- `src/agent_slides/model/layouts.py`

### Manifest lane (future)
Files the agent MAY edit:
- `.artifacts/bcg.manifest.json`
- `src/agent_slides/io/template_reader.py` (slot mapping heuristics only)
- `src/agent_slides/model/template_layouts.py`

### Skill lane (future)
Files the agent MAY edit:
- `skills/create-deck/**`
- `skills/edit-slide/**`
- `skills/learn-template/**`

## Benchmarks to run

Run all three in order:
1. `minimal-title-body` (fast sanity check)
2. `bcg-update` (medium complexity)
3. `bcg-strategy` (full complexity, primary quality target)

Template for all: `examples/bcg.pptx`
Manifest: `.artifacts/bcg.manifest.json`

## Score function

Deterministic metrics (from `scripts/demo_research.py`):
- `build_success`: PPTX builds without error (weight 10)
- `validate_clean`: no validation warnings (weight 20)
- `no_overflow`: no text overflow flags in computed nodes (weight 15)
- `no_unbound`: no unbound nodes (weight 15)
- `placeholder_fill`: % of slots with content (weight 20)
- `layout_variety`: distinct layouts / minimum required (weight 10)
- `slide_count_match`: actual slides within expected range (weight 10)

Composite: weighted average, 0-100 scale.

## Accept/reject rule

- **Accept** if composite >= previous best AND no regression on any individual metric > 10 points
- **Reject** if composite < previous best OR any metric regresses > 10 points
- **Escalate to human** if composite improves but a metric regresses > 5 points (trade-off decision)

## Current hypothesis

The root cause of poor text formatting in template-backed decks is that `_fill_placeholder()`
in `pptx_writer.py` calls `text_frame.clear()` and then explicitly sets font family, size,
and color on every run. This destroys the placeholder's native formatting from the template.

The fix should:
1. Stop setting font properties on template runs unless explicitly overridden in the deck spec
2. Let the template placeholder's native paragraph/run formatting show through
3. Only override when `style_overrides` or `TextRun` specs explicitly request it

## Observations from previous runs

### Run: initial (bcg-demo, manual)
- Slide 1 (title_slide): acceptable
- Slides 2, 6 (section_header_box): text tiny, empty placeholder outlines visible
- Slides 3, 5, 7, 8 (title_and_text): heading blocks in body render at oversized fonts
- Slide 9 (two_col variant): only left column filled
- All slides: font family/size forced from computed state, overriding template defaults

## Experiment history

| Run ID | Lane | Hypothesis | Composite | Decision |
|--------|------|-----------|-----------|----------|
| initial | - | baseline | TBD | baseline |

## When to stop and escalate

- After 3 consecutive rejected runs in the same lane
- When the remaining issues are subjective (color preferences, spacing taste)
- When the fix requires model/types.py changes (cross-cutting, needs human review)
- When tests fail and the root cause is unclear
