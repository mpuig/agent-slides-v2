# AGENTS.md

## Project overview

`agent-slides` is a Python CLI for building PowerPoint decks from a semantic scene graph.

The architectural contract is:

- `deck.json` is the authoring source of truth.
- semantic mutations happen through slides, slots, layouts, themes, and structured text blocks
- reflow derives computed geometry and resolved styles
- `deck.computed.json`, the preview server, and `.pptx` output are downstream consumers of computed state

This repository already ships:

- deck editing and PPTX generation
- separate computed sidecar persistence
- live preview server and watcher
- built-in themes and theme commands
- structured text blocks for slot content
- image nodes, image-capable layouts, preview image rendering, and PPTX image rendering

## Setup commands

- Install dependencies: `uv sync --dev`
- Show CLI help: `uv run agent-slides --help`
- Check version: `uv run agent-slides --version`
- Run the full test suite: `uv run pytest -q`

## Testing instructions

- Run all tests before finishing significant code changes: `uv run pytest -q`
- CLI changes: `uv run pytest -q tests/test_commands.py tests/test_e2e.py`
- Sidecar / computed cache changes: `uv run pytest -q tests/test_sidecar.py tests/test_types.py`
- Reflow, layouts, themes, or image placement changes: `uv run pytest -q tests/test_reflow_images.py tests/test_layouts.py tests/test_validator.py`
- PPTX writer changes: `uv run pytest -q tests/test_pptx_writer.py`
- Preview changes: `uv run pytest -q tests/test_preview.py tests/test_preview_e2e.py`

Do not treat README examples as sufficient verification. The tests are the real behavioral contract.

## Architecture map

- `src/agent_slides/cli.py`: top-level Click CLI with JSON error output
- `src/agent_slides/commands/`: active user-facing command implementations
- `src/agent_slides/model/types.py`: `Deck`, `Slide`, `Node`, `NodeContent`, `ComputedNode`
- `src/agent_slides/model/layouts.py`: built-in layouts and slot roles
- `src/agent_slides/model/themes.py`: theme loading and resolved role styles
- `src/agent_slides/engine/reflow.py`: semantic-to-computed layout engine
- `src/agent_slides/engine/validator.py`: design-rule validation
- `src/agent_slides/io/sidecar.py`: source/computed sidecar read/write and mutation pipeline
- `src/agent_slides/io/pptx_writer.py`: PPTX output
- `src/agent_slides/preview/`: browser preview server, watcher, and HTML client
- `tests/`: primary source of truth for intended behavior

## Workflow rules

### Mutation path

Prefer the shared mutation pipeline in `mutate_deck()`:

1. read `deck.json`
2. apply semantic mutation
3. bump revision
4. reflow whole deck
5. write `deck.json`
6. write `deck.computed.json`

If you add or change commands, route them through `mutate_deck()` rather than open-coding deck reads, writes, or reflow.

### Build path

The `build` command should:

1. read deck
2. reflow deck
3. persist `deck.computed.json`
4. write `.pptx`

Keep the preview/build contract aligned with the computed sidecar.

## Data model conventions

- `Deck.version` is currently `2`
- `Node.type` is `text` or `image`
- text content should live in `NodeContent`, not raw strings at rest
- legacy string content is still accepted and coerced into paragraph blocks
- image nodes must not carry text content
- placeholder image nodes may exist with `style_overrides["placeholder"] == True`
- computed node data is derived state, not authoring state

If you introduce a new node capability, update all affected layers:

1. model types
2. CLI mutation handling
3. reflow
4. preview payload and browser rendering
5. PPTX writer
6. tests

## Layout and theme conventions

- layouts are semantic slot templates, not arbitrary drawing instructions
- slot roles drive text fitting and style resolution
- full-bleed image slots are special-cased in reflow/rendering
- themes define spacing, colors, and fonts used by reflow and rendering

When adding or changing layouts:

- register the layout in `src/agent_slides/model/layouts.py`
- add targeted tests, especially for images, overlays, or full-bleed behavior

## CLI conventions

- success responses should be JSON on stdout
- domain failures should be JSON on stderr via `AgentSlidesError`
- command behavior should stay deterministic and testable

Current live commands:

- `init`
- `slide add`
- `slide remove`
- `slide set-layout`
- `slot set`
- `slot clear`
- `slot bind`
- `theme list`
- `theme apply`
- `build`
- `validate`
- `info`
- `preview`
- `batch`

If you extend `slot set`, preserve the existing mutual-exclusion and validation behavior around text vs image inputs.

## Codebase-specific guidance

- Prefer the live path in `src/agent_slides/commands/mutations.py` plus CLI wrappers.
- `src/agent_slides/commands/ops.py` appears to be leftover code and is not the active CLI path.
- Keep sidecar writes atomic through the helpers in `src/agent_slides/io/sidecar.py`.
- Do not parallelize mutations against the same deck file; temp-file writes will race.
- Preserve relative image-path behavior from the CLI; build resolves image assets relative to the deck path.
- Keep PPTX image behavior aligned with preview and reflow semantics, especially `image_fit`.

## Documentation and history

- `docs/decisions/0001-structured-text-model.md`: structured text rationale

Recent history shows the current shape of the project:

- computed sidecar split
- preview server and preview command
- theme system and theme commands
- structured text content
- image node support
- image-capable layouts
- image rendering in reflow, preview, PPTX, and CLI
- packaging and CI

When unsure how something is supposed to work, inspect the tests for that area first, then the commit history.

## Architecture decisions

### Computed layout persistence

Persist derived layout data in `deck.computed.json`, not in `deck.json`.

Why this is the current contract:

- it keeps `deck.json` as the authoring source of truth instead of mixing source data with derived geometry and resolved styles
- it reduces diff noise and revision churn in the source deck file
- it gives the preview pipeline a clean watch boundary: preview can treat `deck.computed.json` as the signal that reflow finished
- it keeps preview as a thin consumer of computed state instead of forcing it to run the reflow engine on demand

Tradeoffs and mitigations:

- writing two files is not transactionally atomic across the filesystem
- the write order matters: write `deck.json` first, then `deck.computed.json`
- preview should watch the computed sidecar, because that update means the source deck write already completed
- `read_deck()` must ignore computed sidecars whose `deck_id` or `revision` does not match the source deck, so stale cache never becomes source of truth

Rejected alternatives:

- keeping computed layout inside `deck.json` makes diffs noisy and muddies ownership between authoring state and derived state
- computing layout only on demand would couple preview to engine execution and add latency to the preview path

## Pull request guidance

- Keep changes vertical through the stack when necessary; partial-layer feature work is usually incomplete here.
- Run the relevant tests before committing.
- Update README or docs if the user-facing CLI or architecture contract changes.
