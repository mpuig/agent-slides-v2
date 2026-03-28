# AGENTS.md

## Project overview

`agent-slides` is a Python CLI for building PowerPoint decks from a semantic scene graph.

The architectural contract is:

- `deck.json` is the authoring source of truth
- semantic mutations happen through slides, slots, layouts, themes, structured text blocks, charts, and images
- reflow derives computed geometry and resolved styles
- `deck.computed.json`, the preview server, and `.pptx` output are downstream consumers of computed state

The interface contract:

- The CLI is the stable machine interface for agents. All commands return JSON on stdout, errors on stderr.
- Skills (`create-deck`, `edit-slide`, `review-deck`) are the orchestration layer. They teach agents how to use the CLI for complex workflows.
- LLM-specific logic belongs in skills, not in library code. The embedded orchestrators (`orchestrator.py`, `preview/orchestrator.py`) are deprecated and pending removal (#165).
- The preview server is a slide viewer, not a chat host.

## Known issues

- `preview/server.py` image endpoint allows path traversal (#159, high, pending fix)
- Preview WebSocket does not send initial snapshot to new clients (#161)
- `slot set` lacks `--content` flag for structured TextBlock JSON (#170, use `batch` as workaround)
- Template decks do not apply text fitting to placeholder content (#152)

## Setup commands

- Install dependencies: `uv sync --group dev`
- Show CLI help: `uv run agent-slides --help`
- Run the full test suite: `uv run pytest -q`

## Testing instructions

- Run all tests before finishing significant code changes: `uv run pytest -q`
- CLI changes: `uv run pytest -q tests/test_commands.py tests/test_e2e.py`
- Sidecar / computed cache changes: `uv run pytest -q tests/test_sidecar.py tests/test_types.py`
- Reflow, layouts, themes, or image placement changes: `uv run pytest -q tests/test_reflow_images.py tests/test_layouts.py tests/test_validator.py`
- PPTX writer changes: `uv run pytest -q tests/test_pptx_writer.py`
- Preview changes: `uv run pytest -q tests/test_preview.py tests/test_preview_e2e.py`
- Chart changes: `uv run pytest -q tests/test_e2e_charts.py tests/test_pptx_writer.py`
- Template ingestion: `uv run pytest -q tests/test_learn.py tests/test_template_layouts.py tests/test_template_reflow.py tests/test_e2e_template.py`
- Layout suggestion: `uv run pytest -q tests/test_layout_suggest.py`

Do not treat README examples as sufficient verification. The tests are the real behavioral contract.

## Architecture map

### CLI and commands
- `src/agent_slides/cli.py`: top-level Click CLI with JSON error output
- `src/agent_slides/commands/mutations.py`: shared mutation pipeline (`apply_mutation` + `SUPPORTED_MUTATION_COMMANDS`)
- `src/agent_slides/commands/slide.py`: slide add/remove/set-layout (includes `--auto-layout`)
- `src/agent_slides/commands/slot.py`: slot set/clear/bind
- `src/agent_slides/commands/chart.py`: chart add/update
- `src/agent_slides/commands/batch.py`: atomic multi-mutation from JSON stdin
- `src/agent_slides/commands/init.py`: deck creation (`--theme` or `--template`)
- `src/agent_slides/commands/build.py`: PPTX rendering
- `src/agent_slides/commands/learn.py`: template PPTX extraction to manifest
- `src/agent_slides/commands/inspect_cmd.py`: manifest summary
- `src/agent_slides/commands/suggest_layout.py`: layout recommendations from content
- `src/agent_slides/commands/validate_cmd.py`: design-rule validation
- `src/agent_slides/commands/preview.py`: live preview server command
- `src/agent_slides/commands/review.py`: visual QA via LibreOffice rendering
- `src/agent_slides/commands/theme.py`: theme list/apply
- `src/agent_slides/commands/info.py`: sidecar JSON dump

### Model
- `src/agent_slides/model/types.py`: `Deck`, `Slide`, `Node`, `NodeContent`, `TextBlock`, `ComputedNode`, `ChartSpec`, `ChartSeries`, `ScatterSeries`
- `src/agent_slides/model/layouts.py`: built-in layout definitions (12 layouts) and slot roles
- `src/agent_slides/model/layout_provider.py`: `LayoutProvider` protocol, `BuiltinLayoutProvider`, `resolve_layout_provider()`
- `src/agent_slides/model/template_layouts.py`: `TemplateLayoutRegistry` (loads layouts from learned manifest)
- `src/agent_slides/model/themes.py`: theme loading and resolved role styles
- `src/agent_slides/model/design_rules.py`: design rule profiles from YAML config
- `src/agent_slides/model/constraints.py`: constraint types for validator output

### Engine
- `src/agent_slides/engine/reflow.py`: semantic-to-computed layout engine (grid computation, style resolution)
- `src/agent_slides/engine/template_reflow.py`: template-specific reflow (positions from manifest bounds)
- `src/agent_slides/engine/text_fit.py`: character-per-line heuristic with font shrinking
- `src/agent_slides/engine/layout_suggest.py`: rule-based layout suggestion engine
- `src/agent_slides/engine/validator.py`: design-rule validation

### I/O
- `src/agent_slides/io/sidecar.py`: source/computed sidecar read/write, `mutate_deck()` pipeline
- `src/agent_slides/io/pptx_writer.py`: PPTX output (text nodes, image nodes, native chart objects, template-cloned builds)
- `src/agent_slides/io/template_reader.py`: PPTX template extraction to manifest JSON

### Preview
- `src/agent_slides/preview/server.py`: HTTP + WebSocket server with LibreOffice PNG rendering
- `src/agent_slides/preview/renderer.py`: LibreOffice headless slide-to-PNG pipeline
- `src/agent_slides/preview/watcher.py`: file system watcher on computed sidecar
- `src/agent_slides/preview/client.html`: browser preview client

### Skills
- `skills/create-deck/`: deck creation skill with storytelling references
- `skills/edit-slide/`: deck modification skill
- `skills/review-deck/`: visual QA skill

### Tests
- `tests/`: primary source of truth for intended behavior

## Workflow rules

### Mutation path

All mutating commands go through `mutate_deck()`:

1. read `deck.json`
2. resolve `LayoutProvider` (built-in or template)
3. apply semantic mutation via `apply_mutation()`
4. bump revision
5. reflow whole deck (grid reflow or template reflow depending on provider)
6. write `deck.json`
7. write `deck.computed.json`

If you add or change commands, route them through `mutate_deck()` rather than open-coding deck reads, writes, or reflow.

### Build path

The `build` command:

1. read deck
2. resolve layout provider
3. reflow deck
4. persist `deck.computed.json`
5. write `.pptx` (from-scratch path or template-clone path)

## Data model conventions

- `Deck.version` is currently `2`
- `Node.type` is `text`, `image`, or `chart`
- Text content lives in `NodeContent` with `TextBlock` entries (paragraph, bullet, heading types)
- Legacy string content is still accepted and coerced into paragraph blocks
- Image nodes carry `image_path` and `image_fit`
- Chart nodes carry `ChartSpec` with chart type, data series, and styling
- Computed node data is derived state, not authoring state

If you introduce a new node capability, update all affected layers:

1. model types
2. CLI mutation handling
3. reflow
4. preview payload and browser rendering
5. PPTX writer
6. tests

## Layout and theme conventions

- 12 built-in layouts: blank, closing, comparison, gallery, hero_image, image_left, image_right, quote, three_col, title, title_content, two_col
- layouts are semantic slot templates, not arbitrary drawing instructions
- slot roles drive text fitting and style resolution
- full-bleed image slots are special-cased in reflow/rendering
- themes define spacing, colors, and fonts used by reflow and rendering
- the `LayoutProvider` protocol abstracts built-in vs template layouts

When adding or changing layouts:

- register the layout in `src/agent_slides/model/layouts.py`
- add targeted tests, especially for images, overlays, or full-bleed behavior

## CLI conventions

- success responses: JSON on stdout
- domain failures: JSON on stderr via `AgentSlidesError`
- command behavior should stay deterministic and testable

Current live commands:

- `init` (with `--theme` or `--template`)
- `slide add` (with `--layout` or `--auto-layout`)
- `slide remove`
- `slide set-layout`
- `slot set` (text, image, or structured content)
- `slot clear`
- `slot bind`
- `chart add`
- `chart update`
- `theme list`
- `theme apply`
- `build`
- `validate`
- `info`
- `preview`
- `review`
- `batch`
- `learn`
- `inspect`
- `suggest-layout`

## Codebase-specific guidance

- All mutations go through `src/agent_slides/commands/mutations.py` via `apply_mutation()`.
- `ops.py` has been deleted. Do not recreate it.
- `src/agent_slides/orchestrator.py` and `src/agent_slides/preview/orchestrator.py` are deprecated. Do not extend them. They will be removed (#165). New orchestration logic goes in skills.
- Keep sidecar writes atomic through the helpers in `src/agent_slides/io/sidecar.py`.
- Do not parallelize mutations against the same deck file; temp-file writes will race.
- Preserve relative image-path behavior from the CLI; build resolves image assets relative to the deck path.
- The PPTX writer has two code paths: from-scratch (built-in themes) and template-clone (learned templates). Both coexist in `pptx_writer.py`.
- Native PowerPoint bullets use paragraph-level XML formatting (`buChar`), not prepended bullet characters.
- Chart nodes render as native editable PowerPoint chart objects via python-pptx's chart API.
- The preview server renders slides as PNGs via LibreOffice headless when available, falls back to SVG.
- Do not add LLM-specific dependencies (anthropic, openai) to the core package. Agent integration happens through the CLI + skills, not through library imports.

## Architecture decisions

### Computed layout persistence

Persist derived layout data in `deck.computed.json`, not in `deck.json`.

- keeps `deck.json` as the authoring source of truth
- reduces diff noise and revision churn
- gives the preview pipeline a clean watch boundary
- preview watches the computed sidecar as the signal that reflow finished
- `read_deck()` ignores computed sidecars whose `deck_id` or `revision` does not match

### LayoutProvider protocol

The `LayoutProvider` protocol abstracts layout resolution:

- `BuiltinLayoutProvider` wraps the static `LAYOUTS` dict
- `TemplateLayoutRegistry` loads layouts from a learned manifest JSON
- `resolve_layout_provider()` picks the right one based on `deck.template_manifest`
- All commands use the provider, never call `get_layout()` directly

### Template ingestion

- `learn` extracts slide masters, layouts, placeholders, theme from a PPTX
- Produces a manifest JSON with slot mappings using v0 vocabulary (heading, subheading, col1, col2, body, image)
- `build` with a template clones the original PPTX and fills native placeholders via `TextFrame.clear()` + `add_run()`
- Template reflow uses placeholder bounds from the manifest, not the grid engine

## Pull request guidance

- Keep changes vertical through the stack when necessary; partial-layer feature work is usually incomplete.
- Run the relevant tests before committing.
- Update README or docs if the user-facing CLI or architecture contract changes.
