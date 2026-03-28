# CLAUDE.md

Canonical repository guidance lives in `AGENTS.md`. This file keeps the minimum repo-specific context needed for tools that only inject `CLAUDE.md`.

## Project overview

`agent-slides` is a Python CLI for building PowerPoint decks from a semantic scene graph.

Key contract:

- `deck.json` is the authoring source of truth
- semantic mutations happen through slides, slots, layouts, themes, charts, images, and structured text blocks
- reflow derives computed geometry and resolved styles
- `deck.computed.json`, the preview server, and `.pptx` output are downstream consumers of computed state

## Setup and validation

Use `uv` at the repository root.

- install deps: `uv sync --dev`
- CLI help: `uv run agent-slides --help`
- full test suite: `uv run pytest -q`

Targeted validation by area:

- CLI changes: `uv run pytest -q tests/test_commands.py tests/test_e2e.py`
- sidecar / computed cache changes: `uv run pytest -q tests/test_sidecar.py tests/test_types.py`
- reflow, layouts, themes, or image placement: `uv run pytest -q tests/test_reflow_images.py tests/test_layouts.py tests/test_validator.py`
- PPTX writer: `uv run pytest -q tests/test_pptx_writer.py`
- preview: `uv run pytest -q tests/test_preview.py tests/test_preview_e2e.py`

Do not treat README examples as sufficient verification.

## Code paths that matter

- `src/agent_slides/cli.py`: top-level Click CLI with JSON error output
- `src/agent_slides/commands/`: active user-facing commands
- `src/agent_slides/model/types.py`: `Deck`, `Slide`, `Node`, `NodeContent`, `ComputedNode`
- `src/agent_slides/engine/reflow.py`: semantic-to-computed layout engine
- `src/agent_slides/engine/validator.py`: design-rule validation
- `src/agent_slides/io/sidecar.py`: source/computed sidecar read/write and mutation pipeline
- `src/agent_slides/io/pptx_writer.py`: PPTX output
- `src/agent_slides/preview/`: preview server, watcher, and HTML client
- `tests/`: behavioral source of truth

Prefer the live mutation path in `src/agent_slides/commands/mutations.py` plus CLI wrappers. `src/agent_slides/commands/ops.py` is leftover code, not the active path.

## Workflow rules

### Mutation path

Prefer the shared mutation pipeline in `mutate_deck()`:

1. read `deck.json`
2. apply semantic mutation
3. bump revision
4. reflow whole deck
5. write `deck.json`
6. write `deck.computed.json`

Do not open-code deck reads, writes, or reflow in commands when the shared pipeline already exists.

### Build path

The `build` command should:

1. read deck
2. reflow deck
3. persist `deck.computed.json`
4. write `.pptx`

Keep the preview/build contract aligned with the computed sidecar.

## Data model and rendering conventions

- `Deck.version` is currently `2`
- `Node.type` is `text`, `image`, or `chart`
- text content should live in `NodeContent`, not raw strings at rest
- legacy string content is still accepted and coerced into paragraph blocks
- image nodes must not carry text content
- computed node data is derived state, not authoring state

If you add a node capability, update all affected layers:

1. model types
2. CLI mutation handling
3. reflow
4. preview payload and browser rendering
5. PPTX writer
6. tests

## Computed layout persistence

Persist derived layout data in `deck.computed.json`, not in `deck.json`.

Why:

- keeps `deck.json` as the authoring source of truth
- reduces diff noise from derived geometry and resolved styles
- gives preview a clean watch boundary for "reflow finished"
- keeps preview as a thin consumer instead of requiring on-demand reflow execution

Operational rules:

- write `deck.json` first, then `deck.computed.json`
- preview should watch `deck.computed.json`
- `read_deck()` must ignore computed sidecars whose `deck_id` or `revision` does not match the source deck

For fuller repository guidance, see `AGENTS.md`.
