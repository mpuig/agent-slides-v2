# Demo Research Program

This file is the evolving research policy for the demo quality loop.
It controls what the experiment cycle agent does on each run.

## Current lane

**engine** — ensure all usable template layouts render correctly when filled with content.

## Lane boundaries

### Engine lane (current)
Files the agent MAY edit:
- `src/agent_slides/io/pptx_writer.py`
- `src/agent_slides/io/template_reader.py`
- `src/agent_slides/engine/reflow.py`
- `src/agent_slides/engine/validator.py`
- `src/agent_slides/engine/text_fit.py`
- `tests/test_pptx_writer.py`
- `tests/test_learn.py`
- `tests/test_template_reflow.py`
- `tests/test_e2e_template.py`
- `tests/test_validator.py`

Files the agent MUST NOT edit:
- `skills/**`
- `benchmarks/**`
- `program-demo.md`
- `src/agent_slides/commands/**`
- `src/agent_slides/model/layouts.py`

### Manifest lane (future)
Files the agent MAY edit:
- `.artifacts/*.manifest.json`
- `src/agent_slides/io/template_reader.py` (slot mapping heuristics only)
- `src/agent_slides/model/template_layouts.py`

### Skill lane (future)
Files the agent MAY edit:
- `skills/create-deck/**`
- `skills/edit-slide/**`
- `skills/learn-template/**`

## Benchmarks to run

Run all four in order:
1. `minimal-title-body` (fast sanity check)
2. `quarterly-update` (medium complexity)
3. `strategy-deck` (full complexity)
4. `layout-showcase` (layout coverage, primary target for this round)

Template for all: the learned manifest in `.artifacts/`

## Score function

Metrics (from `scripts/demo_research.py`):
- `review_quality`: rendered visual quality from LibreOffice screenshots, passed/total on 38-item checklist (weight 25)
- `build_success`: PPTX builds without error (weight 10)
- `validate_clean`: no validation warnings (weight 10)
- `no_overflow`: no text overflow flags in computed nodes (weight 10)
- `no_unbound`: no unbound nodes (weight 10)
- `placeholder_fill`: % of text slots with content (weight 10)
- `layout_coverage`: required layouts present in deck (weight 15)
- `slide_count_match`: actual slides within expected range (weight 10)

Composite: weighted average, 0-100 scale.

The review_quality metric is the primary quality signal — it measures actual rendered
slide quality, not structural proxies. Changes that improve structural metrics but
degrade review_quality should be rejected.

## Accept/reject rule

- **Accept** if composite >= previous best AND review_quality does not regress > 5 points
- **Reject** if composite < previous best OR review_quality regresses > 5 points
- **Escalate to human** if composite improves but review_quality regresses > 2 points

## Current hypothesis

Many heading-only layouts (arrow variants, green panels, one-third/half/two-third splits)
have not been tested with actual content. They may have:
1. Placeholder bounds too small for typical heading text, causing overflow
2. Font size ranges that don't match the placeholder dimensions
3. Missing paragraph formatting preservation for non-standard placeholder types
4. Image placeholder slots that fail silently when no image is provided

The layout-showcase benchmark exercises all 20 distinct layout categories in one deck.
Failures will reveal which layouts need engine-level fixes.

## Observations from previous runs

### Round 1: Engine formatting (cycles 1-10)
- Baseline: 53.9 → Final: 96.7
- Fixed: font override in template runs, paragraph formatting preservation,
  validator false positives, multi-line text fitting for narrow placeholders
- Remaining: all fixes validated only against title_slide, title_and_text,
  big_statement_green, section_header_*, and d_gray_slice_heading

### Round 2: Layout coverage (cycles 11-16)
- Baseline: 89.0 → Best: 97.0
- Fixed: constrained placeholder font suppression, area-scaled word limits,
  width-aware text fitting, image placeholder filling
- Finding: composite was optimizing structural proxies, not rendered quality.
  Scoring updated to weight review_quality at 25%.

## Experiment history

| Run ID | Lane | Hypothesis | Composite | Decision |
|--------|------|-----------|-----------|----------|
| baseline | - | baseline | 53.9 | baseline |
| cycle-03 | engine | stop overwriting template fonts | 80.5 | accept |
| cycle-04 | engine | validator template slug recognition | 95.1 | accept |
| cycle-06 | engine | preserve paragraph XML (pPr) | 95.1 | accept |
| cycle-07 | scoring | exclude unfillable image slots | 96.7 | accept |
| cycle-08 | engine | multi-line font shrinking | 96.6 | accept |
| cycle-12 | engine | constrained placeholder font suppression | 96.0 | accept |
| cycle-15 | engine | width-aware text fitting | 97.0 | accept |
| cycle-16 | engine | area-scaled word limits | 96.0 | accept |

## When to stop and escalate

- After 3 consecutive rejected runs in the same lane
- When the remaining issues are subjective (color preferences, spacing taste)
- When the fix requires model/types.py changes (cross-cutting, needs human review)
- When tests fail and the root cause is unclear
