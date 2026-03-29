---
name: demo-cycle
description: Run one experiment cycle of the demo research loop. Reads program-demo.md for the current lane and hypothesis, applies a fix, builds all benchmarks, scores them, and records results.
---

# Demo Research Cycle

You are running one experiment cycle of the autoresearch-inspired demo quality loop.

## Setup

1. Read `program-demo.md` to understand:
   - The current **lane** (which files you may edit)
   - The current **hypothesis** (what to fix)
   - The **accept/reject rule** (review_quality is the primary quality gate)
   - **Observations from previous runs** (what went wrong)
   - **Experiment history** (previous scores)

2. Read `AGENTS.md` for architecture context.

## Phase 1: Understand the problem

1. Read the files listed in the lane boundaries for the current lane.
2. If previous run artifacts exist in `runs/`, read the most recent `summary.json` to understand the baseline.
3. Form a specific, testable fix plan based on the hypothesis in `program-demo.md`.

## Phase 2: Apply the fix

1. Make the smallest change that tests the hypothesis.
2. Stay strictly within the lane boundaries. Do NOT edit files outside the allowed list.
3. Run the relevant tests from AGENTS.md to verify you haven't broken anything:
   - Engine lane: `uv run pytest -q tests/test_pptx_writer.py tests/test_learn.py tests/test_e2e_template.py tests/test_template_reflow.py`
   - Manifest lane: `uv run pytest -q tests/test_learn.py tests/test_template_layouts.py tests/test_e2e_template.py`
   - Skill lane: no unit tests, but validate with `uv run agent-slides validate`

## Phase 3: Build all benchmarks

For each benchmark listed in `program-demo.md` (currently 4):

1. Read the brief markdown file in `benchmarks/`.
2. Learn the template if no manifest exists in `.artifacts/`.
3. Initialize a deck with the template:
   ```
   uv run agent-slides init runs/<run_id>/<benchmark>/deck.json --template <manifest_path>
   ```
4. Build the deck content following the brief:
   - Use **explicit layout slugs** from the brief when specified (e.g., layout-showcase requires specific layouts per slide). Do NOT use `--auto-layout` for benchmarks with required layouts.
   - Use `--auto-layout` only for benchmarks without required layouts (e.g., strategy-deck, quarterly-update).
   - For image-required layouts, use real images from `examples/images/` — pick images by matching tags in `examples/images/index.json`.
   - Use `slide add`, `slot set`, and `batch` commands.
5. Build the PPTX:
   ```
   uv run agent-slides build runs/<run_id>/<benchmark>/deck.json -o runs/<run_id>/<benchmark>/deck.pptx
   ```

Use a timestamp-based run ID: YYYYMMDD-HHMMSS format.

## Phase 4: Score

Run the scoring pipeline:
```
uv run python scripts/demo_research.py --run-id <run_id>
```

This scores all benchmarks and writes `runs/<run_id>/summary.json`.

The composite includes `review_quality` (weight 25) which measures actual rendered
slide quality via LibreOffice screenshots. This is the primary quality signal.

## Phase 5: Record and decide

1. Read the new `summary.json`.
2. Compare against the previous best run (if any).
3. Apply the accept/reject rule from `program-demo.md`:
   - **Accept**: composite >= previous best AND review_quality does not regress > 5 points
   - **Reject**: composite < previous best OR review_quality regresses > 5 points
   - **Escalate**: composite improves but review_quality regresses > 2 points
4. Write a short summary to `runs/<run_id>/decision.md` with:
   - What was changed
   - Score delta (including review_quality specifically)
   - Decision (accept/reject/escalate)
   - What to try next

5. If **rejected**: revert the code changes (`git checkout -- <files>`). The run artifacts stay for analysis.
6. If **accepted**: keep the changes (do not commit — the human will review and commit).
7. If **escalate**: keep the changes but flag clearly in decision.md.

## Constraints

- ONE hypothesis per cycle. Do not fix multiple things at once.
- Do NOT edit `program-demo.md`. The human updates the policy.
- Do NOT commit changes. Leave them as unstaged modifications.
- Do NOT edit files outside the current lane boundaries.
- If tests fail after your change, revert and record the failure in decision.md.
