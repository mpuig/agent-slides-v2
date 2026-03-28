# agent-slides

A Python CLI for building PowerPoint decks from a semantic scene graph. Mutate a JSON sidecar, the engine reflows content into layout slots, validates against design rules, and emits a `.pptx` file.

The key idea: deck edits are structural. Add a slide, switch layouts, set slot content, add a chart, and regenerate the presentation without pixel-pushing or manual alignment.

## Installation

```bash
pip install agent-slides
```

For development:

```bash
uv sync --group dev
```

## Quick Start

```bash
agent-slides init deck.json
agent-slides slide add deck.json --layout title
agent-slides slot set deck.json --slide 0 --slot heading --text "Ship the board deck in minutes"
agent-slides slot set deck.json --slide 0 --slot subheading --text "Semantic operations, deterministic reflow, PowerPoint output"
agent-slides build deck.json -o deck.pptx
```

## Command Reference

### Deck management

| Command | Description |
| --- | --- |
| `init PATH [--theme THEME] [--rules RULES] [--template MANIFEST] [--force]` | Create a new deck. `--template` and `--theme` are mutually exclusive. |
| `build PATH -o FILE` | Reflow, persist computed data, render `.pptx`. |
| `validate PATH` | Check design rules, emit structured warnings. |
| `info PATH` | Print the full sidecar JSON. |
| `preview PATH [--port PORT] [--no-open]` | Start live preview server with LibreOffice-rendered slide PNGs. |
| `review PATH [--output-dir DIR] [--dpi N] [--fix]` | Visual QA: render slides to PNG, score against checklist, optionally auto-fix. |
| `batch PATH` | Read JSON array of mutations from stdin, apply atomically. |

### Slide operations

| Command | Description |
| --- | --- |
| `slide add PATH --layout LAYOUT` | Append a slide with the given layout. |
| `slide add PATH --auto-layout --content JSON [--image-count N]` | Append a slide with engine-suggested layout based on content. |
| `slide remove PATH --slide REF` | Remove a slide by index or slide_id. |
| `slide set-layout PATH --slide REF --layout LAYOUT` | Change layout, rebind content to matching slots. |

### Slot operations

| Command | Description |
| --- | --- |
| `slot set PATH --slide REF --slot SLOT --text TEXT` | Set text content in a slot. |
| `slot set PATH --slide REF --slot SLOT --image PATH` | Set image content in a slot. |
| `slot set PATH --slide REF --slot SLOT --content JSON` | Set structured content (TextBlocks). |
| `slot clear PATH --slide REF --slot SLOT` | Clear a slot's content. |
| `slot bind PATH --node NODE_ID --slot SLOT` | Rebind an unbound node to a slot. |

### Chart operations

| Command | Description |
| --- | --- |
| `chart add PATH --slide REF --slot SLOT --type TYPE --data JSON` | Add a native PowerPoint chart. Types: bar, column, line, pie, scatter, area, doughnut. |
| `chart update PATH --node NODE_ID --data JSON` | Update chart data on an existing chart node. |

### Theme operations

| Command | Description |
| --- | --- |
| `theme list` | List built-in themes. |
| `theme apply PATH --theme THEME` | Switch a deck to a different theme. |

### Template ingestion

| Command | Description |
| --- | --- |
| `learn TEMPLATE.pptx [-o MANIFEST.json]` | Extract layouts, placeholders, and theme from a PPTX template. |
| `inspect MANIFEST.json` | Show what the learner found: usable layouts, slots, theme. |

### Layout suggestion

| Command | Description |
| --- | --- |
| `suggest-layout --content JSON [--image-count N]` | Get ranked layout recommendations for given content. |

## Layout Reference

### Text layouts

| Layout | Slots |
| --- | --- |
| `title` | `heading`, `subheading` |
| `title_content` | `heading`, `body` |
| `two_col` | `heading`, `col1`, `col2` |
| `three_col` | `heading`, `col1`, `col2`, `col3` |
| `comparison` | `heading`, `left_header`, `left_body`, `right_header`, `right_body` |
| `quote` | `quote`, `attribution` |
| `closing` | `body` |
| `blank` | (none) |

### Image layouts

| Layout | Slots |
| --- | --- |
| `image_left` | `image`, `heading`, `body` |
| `image_right` | `heading`, `body`, `image` |
| `hero_image` | `image`, `heading`, `subheading` |
| `gallery` | `heading`, `img1`, `img2`, `img3`, `img4` |

## Theme Reference

| Theme | Character | Heading / body fonts |
| --- | --- | --- |
| `academic` | Serif style for reports and lectures | Georgia / Times New Roman |
| `corporate` | Neutral executive deck | Georgia / Arial |
| `dark` | Dark surface, high contrast | Arial / Calibri |
| `default` | Balanced baseline | Calibri / Calibri |
| `startup` | High energy, warm accent | Helvetica / Arial |

## Skills

Three skills ship with the project in `skills/`:

| Skill | Purpose |
| --- | --- |
| `create-deck` | Build a deck from a brief: pre-flight questions, Pyramid Principle storyline, build, QA. |
| `edit-slide` | Modify an existing deck: inspect, smallest mutation, validate. |
| `review-deck` | Visual QA: LibreOffice-rendered screenshots scored against a checklist. |

These skills are the LLM interface. Agents drive the conversation; `agent-slides` stays model-agnostic and exposes deterministic CLI commands plus the preview viewer.

Symlink to `.claude/skills/` for Claude Code integration:

```bash
ln -sf $(pwd)/skills/create-deck .claude/skills/create-deck
ln -sf $(pwd)/skills/edit-slide .claude/skills/edit-slide
ln -sf $(pwd)/skills/review-deck .claude/skills/review-deck
```

## Conversational Workflow

The agent (Claude Code, Codex, Cursor) is the conversational interface. The preview is a slide viewer. No separate chat UI.

```
Terminal (agent)                    Browser (preview)
  User: "make a deck about X"        agent-slides preview deck.json
  Agent loads create-deck skill       → slides appear as agent builds
  Agent runs CLI commands             → preview auto-updates via WebSocket
  Agent runs validate + QA            → pixel-perfect via LibreOffice
  Agent runs build -o deck.pptx       → user opens PPTX
```

Start the preview in one terminal, talk to the agent in another. The agent runs CLI commands, the preview updates automatically.

## Architecture

Scene-graph model with two-file persistence:

- `deck.json` is the source of truth (slides, nodes, theme, layout bindings)
- `deck.computed.json` is the derived cache (positions, resolved styles)
- `.pptx` is the output artifact
- The preview server watches `deck.computed.json` and pushes updates via WebSocket

Node types: `text` (structured TextBlocks with paragraph, bullet, heading types), `image`, `chart` (native editable PowerPoint charts).

The LayoutProvider protocol abstracts built-in layouts from template-learned layouts, so commands work identically in both modes.

## System Dependencies

For pixel-perfect preview rendering (optional, falls back to SVG):

- `soffice` (LibreOffice headless): `brew install libreoffice` / `apt install libreoffice-core`
- `pdftoppm` (poppler-utils): `brew install poppler` / `apt install poppler-utils`

## Development

```bash
uv sync --group dev          # install dependencies
uv run pytest -v             # run tests
uv run agent-slides --help   # CLI help
```
