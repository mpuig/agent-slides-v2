# agent-slides

`agent-slides` is a Python CLI for building PowerPoint decks from a semantic scene graph instead of hand-editing slides. You mutate a JSON sidecar, the engine reflows content into layout slots, validates against design rules, and emits a `.pptx` artifact.

The whoa moment is that deck edits stay structural. You can add a slide, switch layouts, rewrite a slot, and regenerate the presentation without chasing coordinates or manually fixing text boxes.

## Installation

```bash
pip install agent-slides
```

Or install it as an isolated CLI:

```bash
pipx install agent-slides
```

## Quick Start

Five commands from empty directory to generated PowerPoint:

```bash
agent-slides init demo.json --theme startup
agent-slides slide add demo.json --layout title
agent-slides slot set demo.json --slide slide-1 --slot heading --text "Ship the board deck in minutes"
agent-slides slot set demo.json --slide slide-1 --slot subheading --text "Semantic operations, deterministic reflow, PowerPoint output"
agent-slides build demo.json --output demo.pptx
```

What that does:

- Creates a sidecar JSON deck file with the built-in `startup` theme and default design rules.
- Appends a new `title` slide with stable `slide_id` and slot definitions.
- Fills semantic slots rather than editing text boxes directly.
- Reflows the slide and writes a `demo.pptx` file.

## Command Reference

| Command | Description |
| --- | --- |
| `agent-slides init PATH [--theme THEME] [--rules RULES] [--force]` | Create a new deck sidecar JSON file. |
| `agent-slides slide add PATH --layout LAYOUT` | Append a slide using a named built-in layout. |
| `agent-slides slide remove PATH --slide REF` | Remove a slide by index or stable `slide_id`. |
| `agent-slides slide set-layout PATH --slide REF --layout LAYOUT` | Change a slide layout and rebind slot-bound nodes. |
| `agent-slides slot set PATH --slide REF --slot SLOT --text TEXT` | Set text for a slot on a specific slide. |
| `agent-slides theme list` | List the built-in themes available to the CLI. |
| `agent-slides theme apply PATH --theme THEME` | Switch an existing deck to a different built-in theme. |
| `agent-slides build PATH --output FILE` | Reflow the deck, persist computed layout data, and render a `.pptx`. |
| `agent-slides review PATH [--output-dir DIR] [--dpi N] [--fix]` | Build the deck, render slide screenshots through LibreOffice + `pdftoppm`, score visual quality, and optionally apply common auto-fixes. |
| `agent-slides validate PATH` | Run design-rule validation and emit structured warnings. |
| `agent-slides info PATH` | Print the full sidecar JSON with indentation. |
| `agent-slides preview PATH [--port PORT] [--no-open]` | Start the live preview server and optionally suppress automatic browser launch. |
| `agent-slides batch PATH` | Read a JSON array of mutations from stdin and apply them atomically. |

## Layout Reference

Built-in layouts ship with semantic slot names instead of absolute coordinates:

| Layout | Slots |
| --- | --- |
| `blank` | none |
| `closing` | `body` |
| `comparison` | `heading`, `left_header`, `left_body`, `right_header`, `right_body` |
| `quote` | `quote`, `attribution` |
| `three_col` | `heading`, `col1`, `col2`, `col3` |
| `title` | `heading`, `subheading` |
| `title_content` | `heading`, `body` |
| `two_col` | `heading`, `col1`, `col2` |

## Theme Reference

Five built-in themes are packaged with the CLI today:

| Theme | Character | Heading / body fonts |
| --- | --- | --- |
| `academic` | Clean serif presentation style for reports and lectures | `Georgia` / `Times New Roman` |
| `corporate` | Neutral executive deck with restrained accent color | `Georgia` / `Arial` |
| `dark` | Dark-surface presentation with high-contrast text | `Arial` / `Calibri` |
| `default` | Balanced baseline theme for general-purpose decks | `Calibri` / `Calibri` |
| `startup` | High-energy theme with wider spacing and warm accent color | `Helvetica` / `Arial` |

## Architecture Overview

`agent-slides` follows a scene-graph architecture:

- The sidecar JSON is the source of truth for deck structure, slides, nodes, theme selection, design rules, and revision state.
- CLI mutation commands update semantic objects such as slides, slots, and layouts instead of raw PowerPoint coordinates.
- The reflow engine converts those semantic objects into computed layout data using the selected layout template, theme spacing, and text-fitting rules.
- The validator checks the deck against packaged design rules and emits structured warnings before or after rendering.
- The PPTX writer consumes the computed scene graph and produces the final `.pptx` artifact.
- The preview server serves the same computed model to a browser client for live iteration.

## Visual QA

`agent-slides review` is the rendered QA companion to `validate`.

- `validate` checks structural rules such as overflow, hierarchy, and content limits from computed deck state.
- `review` builds the `.pptx`, renders it to slide PNGs via LibreOffice headless and `pdftoppm`, then scores the deck against a visual checklist with screenshot-backed evidence.
- `review --fix` applies a small set of common mechanical fixes, rerenders the deck, and records before/after comparison artifacts.

By default the review artifacts land in `<deck-stem>.review/` next to the source deck and include `report.md`, `report.json`, and rendered slide PNGs.

## Development Notes

For deeper design and architecture rationale, see [docs/decisions/0001-structured-text-model.md](./docs/decisions/0001-structured-text-model.md).
