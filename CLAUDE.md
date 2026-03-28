# agent-slides

Python CLI for LLM agents to create PPTX presentations through semantic deck operations.

## Quick Start

- `uv sync --group dev --frozen`
- `uv run agent-slides --help`
- `uv run pytest -v`

## Architecture Overview

`deck.json` is the authoring source of truth for the scene graph (`Deck -> Slide -> Node`).
`deck.computed.json`, preview state, template manifests, and `.pptx` output are derived artifacts.
See [docs/architecture.md](docs/architecture.md) for the full architecture map.

## Key Concepts

- **Sidecar model**: authoring data lives in `deck.json`; computed layout cache lives in `deck.computed.json`.
- **Layout providers**: the `LayoutProvider` protocol abstracts built-in layouts and learned template manifests.
- **Mutation pipeline**: CLI mutations flow through `mutate_deck()` and persist atomically after reflow.
- **Node types**: nodes can render text, images, or charts.
- **Structured text**: text content is stored as `NodeContent` with `TextBlock` entries.
- **Derived consumers**: preview, build, and template-backed layout flows all read computed state downstream.

## CLI Surface

Primary commands cover deck init, slide and slot mutations, chart operations, themes, validation, build,
preview, batch mutations, template learn/inspect flows, and layout suggestions.
See [docs/cli-reference.md](docs/cli-reference.md) for command details and examples.

## Testing

- Test framework: `pytest`
- Full suite: `uv run pytest -v`
- CLI tests use Click's `CliRunner`
- Behavioral contracts live under `tests/test_*.py`

## Project Conventions

- CLI success output is JSON on stdout; domain failures are JSON on stderr.
- Shared application error codes live in `src/agent_slides/errors.py`.
- Built-in layouts use the v0 slot vocabulary documented in `src/agent_slides/model/layouts.py`.
- Default design rules live in `src/agent_slides/config/design_rules/default.yaml`.
- ADRs live under `docs/decisions/`.

## Docs

- [Architecture](docs/architecture.md) - scene graph, mutation pipeline, reflow engine, derived artifacts
- [CLI Reference](docs/cli-reference.md) - commands, flags, and JSON response shapes
- [Template Ingestion](docs/template-ingestion.md) - `learn`, `inspect`, and manifest-backed layouts
- [Charts](docs/charts.md) - chart node schema, data formats, reflow, and PPTX rendering
- [Auto-Layout](docs/auto-layout.md) - layout suggestion engine and `suggest-layout`
- [Preview Server](docs/preview-server.md) - HTTP server, watcher, WebSocket updates, and SVG rendering
- [Decisions](docs/decisions/) - architecture decision records, including computed layout persistence
