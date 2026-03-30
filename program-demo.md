# Demo Research Program

This file is the evolving research policy for the demo quality loop.
It controls what the experiment cycle agent does on each run.

## Two-layer architecture

The benchmark system now has two independent layers:

1. **Certification layer**
   - Runs deterministic certification across every `examples/*.pptx` template.
   - Produces per-template `coverage.json` artifacts plus `layers.certification` in `runs/<run_id>/summary.json`.
   - Owns the per-layout regression gate.

2. **Demo layer**
   - Scores the realistic benchmark briefs (`minimal-title-body`, `bcg-update`, `bcg-strategy`).
   - Produces `runs/<run_id>/demo-summary.json` plus `layers.demo` in `runs/<run_id>/summary.json`.
   - Owns the mean-composite and `review_quality` gate.

These layers run independently. Certification failures do not block demo execution.

## Generalization rule

Engine fixes must improve certification across multiple templates. If a change only improves one
template, it belongs in template manifests, learned metadata, or benchmark setup rather than in
shared engine code.

## Current lane

**skill** — improve content quality in create-deck to raise review_quality scores across all layouts.

## Lane boundaries

### Skill lane (current)
Files the agent MAY edit:
- `skills/create-deck/**`
- `skills/edit-slide/**`

Files the agent MUST NOT edit:
- `src/**`
- `tests/**`
- `benchmarks/**`
- `program-demo.md`

### Engine lane
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

### Manifest lane
Files the agent MAY edit:
- `.artifacts/*.manifest.json`
- `src/agent_slides/io/template_reader.py` (slot mapping heuristics only)
- `src/agent_slides/model/template_layouts.py`

## Benchmarks to run

Run all four in order:
1. `minimal-title-body` (fast sanity check)
2. `quarterly-update` (medium complexity)
3. `strategy-deck` (full complexity)
4. `layout-showcase` (full layout coverage, primary target for this round — uses ALL non-d_ usable layouts from the manifest)

Template: `examples/bcg.pptx`
Manifest: `.artifacts/bcg.manifest.json`

## Score function

Metrics (from `scripts/demo_research.py`):
- `review_quality`: rendered visual quality from LibreOffice screenshots, passed/total on 38-item checklist (weight 20, primary quality signal)
- `validate_clean`: no validation warnings (weight 20)
- `no_overflow`: no text overflow flags (weight 15)
- `no_unbound`: no unbound nodes (weight 15)
- `placeholder_fill`: % of text slots with content (weight 20)
- `layout_coverage`: required layouts present in deck (weight 10)
- `slide_count_match`: actual slides within expected range (weight 10)
- `build_success`: PPTX builds without error (weight 10)

Brief compliance cap: narrow_headings_ok and source_lines enforce layout-showcase requirements.
When review unavailable: exclude review_quality from composite, flag as review_unavailable.

## Accept/reject rule

- **Accept** if composite >= previous best AND review_quality does not regress > 0.05 per benchmark
- **Reject** if composite regresses OR review_quality regresses > 0.05 on any benchmark
- **Reject** if baseline had review data but current run does not
- **Reject** if any layout that previously passed now fails (per-layout regression gate)

## Current hypothesis

The engine is near-optimal (structural metrics ~97). The remaining quality gap is content-driven:
1. Sparse content — 3 bullets/slide instead of 6-8 in consulting decks
2. Generic titles — "Executive Summary" instead of action titles with conclusions
3. Missing source lines — no attributions on data slides
4. Too many empty section dividers — 2 in 10 slides is excessive
5. Narrow layouts get long headings that overflow

The create-deck skill prompt needs stronger instructions for:
- Dense body content with sub-headings
- Action titles (complete sentences with "so what")
- Source attribution on every data slide
- Short headings for narrow layouts
- Filling all available slots including quote, agenda, and body-only layouts

## Observations from previous runs

### Round 1: Engine formatting (cycles 1-10)
- Baseline: 53.9 → Final: 96.7
- Fixed: font override, paragraph preservation, validator false positives, text fitting

### Round 2: Layout coverage (cycles 11-16)
- Baseline: 89.0 → Best: 97.0
- Fixed: constrained placeholder font suppression, area-scaled word limits, image filling
- Finding: scoring loop was optimizing structural proxies, not rendered quality

### Infrastructure overhaul
- Added review_quality to composite (weight 20)
- Added brief-specific enforcement (required layouts, images, narrow headings, source lines)
- Fixed partial regression detection, review loss rejection, coverage averaging
- Created two-layer architecture (certification + demo)

### Round 3: Content quality + full layout coverage (cycles 17+)
- Starting from: TBD (new baseline with updated scorer)
- Goal: all 37 primary layouts rendered with realistic content, review grades B+ or higher
- Lane: skill (create-deck prompt improvements)

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
- When review grades plateau above B (diminishing returns)
- When tests fail and the root cause is unclear
