#!/bin/bash
# Run one demo research cycle as a new Claude Code session.
# Usage: ./scripts/run_cycle.sh
#
# This spawns a headless Claude Code session that:
# 1. Reads program-demo.md for the current lane/hypothesis
# 2. Applies a fix within lane boundaries
# 3. Builds all benchmarks and scores them
# 4. Records accept/reject decision
#
# Results land in runs/<timestamp>/.

set -euo pipefail
cd "$(dirname "$0")/.."

PROMPT='You are running one experiment cycle of the demo research loop.

## Instructions

1. Read `program-demo.md` to understand the current lane, hypothesis, and accept/reject rules.
2. Read `.claude/skills/demo-cycle/SKILL.md` for the full workflow.
3. Follow the skill instructions exactly — one hypothesis, one lane, smallest change.
4. Use `uv run python scripts/demo_research.py` to score after building.
5. Record your decision in `runs/<run_id>/decision.md`.
6. If rejected, revert code changes. If accepted, leave changes unstaged for human review.

IMPORTANT:
- Do NOT edit files outside the current lane boundaries listed in program-demo.md.
- Do NOT commit changes.
- Do NOT edit program-demo.md.
- Run tests before building benchmarks.
- Use timestamp format YYYYMMDD-HHMMSS for run IDs.
- The baseline score is 53.9 (composite). Beat it.'

echo "Starting demo research cycle..."
claude --print "$PROMPT"
