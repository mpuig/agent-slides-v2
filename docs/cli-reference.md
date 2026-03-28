# CLI Reference

This reference covers the current `agent-slides` CLI surface verified against the checked-in code with `uv run agent-slides ...`.

## Output conventions

### Success envelope

Most commands print a JSON success envelope to stdout:

```json
{
  "ok": true,
  "data": {}
}
```

### Error envelope

Domain errors print a JSON error envelope to stderr and exit with status `1`:

```json
{
  "ok": false,
  "error": {
    "code": "SCHEMA_ERROR",
    "message": "Human-readable message"
  }
}
```

### Exceptions and warnings

- `info` prints the raw deck sidecar JSON instead of the `{"ok": true, "data": ...}` envelope.
- `preview` prints one success payload when the server starts and a second success payload with `{"stopped": true}` when it shuts down.
- `learn` may print human-readable warnings to stderr before its JSON success payload.
- `slide set-layout` may print a JSON warning payload to stderr before its JSON success payload when rebinding leaves nodes unbound.

## Slide references

Commands that accept `--slide` resolve slides in one of two ways:

- Zero-based slide index such as `0` or `1`
- Stable `slide_id` such as `s-1`

Examples:

```bash
agent-slides slide remove deck.json --slide 0
agent-slides slide remove deck.json --slide s-3
```

## Slot vocabulary

These slot names are the canonical vocabulary used by the built-in layouts, learned templates, agents, and skills:

| Slot | Typical use |
| --- | --- |
| `heading` | Primary slide title |
| `subheading` | Secondary title or subtitle |
| `body` | Main paragraph or bullet content |
| `col1` | First body column |
| `col2` | Second body column |
| `col3` | Third body column |
| `quote` | Quotation text |
| `attribution` | Quote source or citation |
| `image` | Primary image placeholder |

The mutation layer also accepts these aliases:

| Alias | Normalized slot |
| --- | --- |
| `title` | `heading` |
| `subtitle` | `subheading` |
| `left` | `col1` |
| `right` | `col2` |

Some layouts expose additional layout-specific names such as `left_header`, `right_body`, or `img1` through `img4`. Those are valid only when the active layout defines them.

## Error codes

The table below lists every code defined in [`src/agent_slides/errors.py`](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_113/src/agent_slides/errors.py).

| Code | Typical source | Meaning |
| --- | --- | --- |
| `INVALID_SLIDE` | slide, slot, chart mutations | Slide index or `slide_id` does not exist |
| `INVALID_SLOT` | slot and chart mutations | Slot name is not valid for the current layout |
| `INVALID_LAYOUT` | `slide add`, `slide set-layout`, layout loading | Layout name is unknown |
| `FILE_NOT_FOUND` | deck reads, image reads, template reads, data-file reads | Referenced file does not exist |
| `SCHEMA_ERROR` | argument parsing, malformed JSON, invalid manifest/template structure | Input shape is invalid |
| `OVERFLOW` | validator warnings | Text overflows the allowed bounds |
| `UNBOUND_NODES` | validator warnings, `slide set-layout` warning payload | Nodes are no longer bound to a slot |
| `IMAGE_NOT_SUPPORTED` | image rendering and asset handling | Image format cannot be processed |
| `INVALID_CHART_TYPE` | chart creation or validation | Chart type is not one of the supported chart kinds |
| `INVALID_NODE_TYPE` | `chart update` | Command targeted the wrong node type |
| `REVISION_CONFLICT` | sidecar writes | Deck changed on disk between read and write |
| `SLOT_OCCUPIED` | slot mutations | Slot is already occupied in a context that forbids replacement |
| `FILE_EXISTS` | `init` and other guarded writes | Output file already exists |
| `TEMPLATE_CHANGED` | PPTX build warnings | Learned template source changed since manifest extraction |
| `CHART_DATA_ERROR` | chart schema validation | Chart payload shape or values are invalid |
| `THEME_INVALID` | theme loading | Theme file exists but is malformed |
| `THEME_NOT_FOUND` | `init`, `theme apply` | Built-in theme name does not exist |
| `THEME_ROLE_NOT_FOUND` | theme lookups | Theme is missing a required role mapping |

## Commands

### `init`

**Synopsis**

```bash
agent-slides init PATH [--theme THEME | --template MANIFEST] [--rules RULES] [--force]
```

**Description**

Creates a new deck sidecar JSON file. New decks start empty and store the selected built-in theme or learned template manifest reference.

**Example**

```bash
agent-slides init demo.json --theme default
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "deck_id": "bae29b00-f1ab-4248-b580-3749ae9fb61c",
    "theme": "default",
    "design_rules": "default"
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when `--theme` and `--template` are passed together.
- `FILE_EXISTS` when `PATH` already exists and `--force` is not set.
- `THEME_NOT_FOUND` or `THEME_INVALID` when the selected theme cannot be loaded.
- `FILE_NOT_FOUND` when `--template` points at a missing manifest.

### `slide add`

**Synopsis**

```bash
agent-slides slide add PATH --layout LAYOUT
agent-slides slide add PATH --auto-layout --content JSON [--image-count N]
```

**Description**

Appends a new slide. You can either pick a concrete layout yourself or let the suggestion engine choose one from structured text content.

**Example**

```bash
agent-slides slide add auto.json --auto-layout --content "$(cat content.json)"
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_index": 0,
    "slide_id": "s-1",
    "layout": "title_content",
    "auto_selected": true,
    "reason": "Generic text content falls back to the title-and-content layout"
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when `--layout` and `--auto-layout` are combined.
- `SCHEMA_ERROR` when `--auto-layout` is used without `--content`.
- `SCHEMA_ERROR` when `--content` is invalid JSON or fails the `NodeContent` schema.
- `INVALID_LAYOUT` when the named layout does not exist.

### `slide remove`

**Synopsis**

```bash
agent-slides slide remove PATH --slide REF
```

**Description**

Removes one slide from the deck by zero-based index or by `slide_id`.

**Example**

```bash
agent-slides slide remove demo.json --slide s-3
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "removed": "s-3",
    "slide_count": 2
  }
}
```

**Error cases**

- `INVALID_SLIDE` when `REF` does not resolve to a slide.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `slide set-layout`

**Synopsis**

```bash
agent-slides slide set-layout PATH --slide REF --layout LAYOUT
```

**Description**

Changes a slide to a different layout and attempts to rebind its existing slot-bound nodes to the new layout's slots.

**Example**

```bash
agent-slides slide set-layout demo.json --slide 0 --layout two_col
```

**Example stderr**

```json
{
  "ok": true,
  "warning": {
    "code": "UNBOUND_NODES",
    "message": "1 node(s) became unbound during slot rebinding."
  },
  "data": {
    "slide_id": "s-1",
    "unbound_nodes": ["n-2"]
  }
}
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_id": "s-1",
    "layout": "two_col",
    "unbound_nodes": ["n-2"]
  }
}
```

**Error cases**

- `INVALID_SLIDE` when `REF` does not resolve to a slide.
- `INVALID_LAYOUT` when `LAYOUT` is unknown.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `slot set`

**Synopsis**

```bash
agent-slides slot set PATH --slide REF --slot SLOT --text TEXT
agent-slides slot set PATH --slide REF --slot SLOT --image IMAGE_PATH
```

**Description**

Writes text or image content into a single slot. Existing content in that slot is replaced.

**Example**

```bash
agent-slides slot set demo.json --slide 0 --slot heading --text "CLI reference"
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_id": "s-1",
    "slot": "heading",
    "node_id": "n-1",
    "type": "text",
    "text": "CLI reference",
    "content": {
      "blocks": [
        {
          "type": "paragraph",
          "text": "CLI reference",
          "level": 0
        }
      ]
    },
    "image_path": null,
    "image_fit": "contain",
    "font_size": null
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when neither or both of `--text` and `--image` are provided.
- `INVALID_SLIDE` when `REF` does not resolve to a slide.
- `INVALID_SLOT` when the slot is not valid for the slide layout.
- `FILE_NOT_FOUND` when `--image` points at a missing file.

### `slot clear`

**Synopsis**

```bash
agent-slides slot clear PATH --slide REF --slot SLOT
```

**Description**

Deletes whatever nodes are currently bound to a slot and returns the removed node IDs.

**Example**

```bash
agent-slides slot clear demo.json --slide 1 --slot col2
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_id": "s-2",
    "slot": "col2",
    "removed_node_ids": ["n-4"]
  }
}
```

**Error cases**

- `INVALID_SLIDE` when `REF` does not resolve to a slide.
- `INVALID_SLOT` when the slot is not valid for the slide layout.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `slot bind`

**Synopsis**

```bash
agent-slides slot bind PATH --node NODE_ID --slot SLOT
```

**Description**

Rebinds an existing node to a different slot on the same slide. Any conflicting node already occupying that slot is pruned.

**Example**

```bash
agent-slides slot bind demo.json --node n-4 --slot col2
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_id": "s-2",
    "slot": "col2",
    "node_id": "n-4"
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when `NODE_ID` does not exist.
- `INVALID_SLOT` when the target slot is not valid for that node's slide layout.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `chart add`

**Synopsis**

```bash
agent-slides chart add PATH --slide REF --slot SLOT --type TYPE (--data JSON | --data-file FILE) [--title TITLE]
```

**Description**

Creates or replaces a chart node in the target slot. The payload must match the schema for the selected chart type.

**Example**

```bash
agent-slides chart add demo.json \
  --slide 1 \
  --slot col1 \
  --type bar \
  --title "Revenue by quarter" \
  --data-file chart-data.json
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "slide_id": "s-2",
    "slot": "col1",
    "node_id": "n-8",
    "chart_type": "bar"
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when neither or both of `--data` and `--data-file` are provided.
- `INVALID_SLIDE` when `REF` does not resolve to a slide.
- `INVALID_SLOT` when the slot is not valid for the current layout.
- `INVALID_CHART_TYPE` when `--type` is unknown.
- `CHART_DATA_ERROR` when the payload does not match the selected chart type.
- `FILE_NOT_FOUND` when `--data-file` points at a missing JSON file.

### `chart update`

**Synopsis**

```bash
agent-slides chart update PATH --node NODE_ID --data JSON
```

**Description**

Updates the `chart_spec` payload of an existing chart node without changing its slot binding.

**Example**

```bash
agent-slides chart update demo.json \
  --node n-8 \
  --data '{"categories":["Q1","Q2","Q3","Q4"],"series":[{"name":"Revenue","values":[12,18,24,31]}]}'
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "node_id": "n-8",
    "chart_type": "bar",
    "updated": true
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when `NODE_ID` does not exist or `--data` is not a JSON object.
- `INVALID_NODE_TYPE` when `NODE_ID` is not a chart node.
- `CHART_DATA_ERROR` when the updated chart payload is invalid.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `batch`

**Synopsis**

```bash
agent-slides batch PATH < operations.json
```

**Description**

Applies multiple mutations from a JSON array read from stdin and writes the deck atomically once. Each operation uses the same mutation names as the internal mutation layer.

**Example**

```bash
printf '%s' '[{"command":"slide_add","args":{"layout":"closing"}},{"command":"slot_set","args":{"slide":2,"slot":"body","text":"Thanks"}}]' \
  | agent-slides batch demo.json
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "operations": 2,
    "results": [
      {
        "slide_index": 2,
        "slide_id": "s-4",
        "layout": "closing"
      },
      {
        "slide_id": "s-4",
        "slot": "body",
        "node_id": "n-9",
        "type": "text",
        "text": "Thanks",
        "content": {
          "blocks": [
            {
              "type": "paragraph",
              "text": "Thanks",
              "level": 0
            }
          ]
        },
        "image_path": null,
        "image_fit": "contain",
        "font_size": null
      }
    ]
  }
}
```

**Error cases**

- `SCHEMA_ERROR` when stdin is not valid JSON, not an array, or includes unsupported commands.
- Child mutation errors such as `INVALID_SLIDE`, `INVALID_SLOT`, or `CHART_DATA_ERROR` bubble up with an added `operation_index` field.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `suggest-layout`

**Synopsis**

```bash
agent-slides suggest-layout --content JSON_OR_@FILE [--image-count N]
```

**Description**

Scores the built-in layouts against structured text content and returns up to three suggestions ordered by descending fit score.

**Example**

```bash
agent-slides suggest-layout --content @content.json --image-count 0
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "suggestions": [
      {
        "layout": "title_content",
        "score": 0.5,
        "reason": "Generic text content falls back to the title-and-content layout."
      }
    ]
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when `--content @file` points at a missing file.
- `SCHEMA_ERROR` when the content JSON is invalid or does not match the `NodeContent` schema.

### `validate`

**Synopsis**

```bash
agent-slides validate PATH
```

**Description**

Runs the current deck through the validator and returns structured warnings plus a boolean `clean` flag.

**Example**

```bash
agent-slides validate demo.json
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "warnings": [
      {
        "code": "UNBOUND_NODES",
        "severity": "error",
        "message": "Slide contains unbound nodes: n-2.",
        "slide_id": "s-1",
        "node_id": null,
        "node_ids": ["n-2"]
      },
      {
        "code": "MISSING_TITLE_SLIDE",
        "severity": "suggestion",
        "message": "Consider starting the deck with a title slide.",
        "slide_id": "s-1",
        "node_id": null,
        "node_ids": null
      }
    ],
    "clean": false
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the deck file does not exist.
- `SCHEMA_ERROR` when the deck JSON cannot be parsed or validated.

### `build`

**Synopsis**

```bash
agent-slides build PATH --output OUTPUT.pptx
```

**Description**

Reflows the deck, writes the derived computed sidecar, and generates a PowerPoint file.

**Example**

```bash
agent-slides build demo.json --output demo.pptx
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "output": "demo.pptx",
    "slides": 3
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the deck, a referenced image asset, or a template artifact is missing.
- `SCHEMA_ERROR` when the deck or manifest is malformed.
- `TEMPLATE_CHANGED` may be emitted as a warning payload when a learned template no longer matches its source PPTX.

### `info`

**Synopsis**

```bash
agent-slides info PATH
```

**Description**

Prints the full deck JSON, including slides, nodes, computed geometry, and counters. This command is intentionally not wrapped in the common success envelope.

**Example**

```bash
agent-slides info demo.json
```

**Example stdout**

```json
{
  "version": 2,
  "deck_id": "bae29b00-f1ab-4248-b580-3749ae9fb61c",
  "revision": 14,
  "theme": "corporate",
  "design_rules": "default",
  "template_manifest": null,
  "slides": [
    {
      "slide_id": "s-1",
      "layout": "two_col",
      "nodes": [
        {
          "node_id": "n-1",
          "slot_binding": "heading",
          "type": "text"
        }
      ]
    }
  ],
  "_counters": {
    "slides": 4,
    "nodes": 9
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the deck file does not exist.
- `SCHEMA_ERROR` when the deck JSON cannot be parsed or validated.

### `learn`

**Synopsis**

```bash
agent-slides learn TEMPLATE.pptx [-o MANIFEST.json]
```

**Description**

Extracts slide layouts, placeholder geometry, slot mappings, and theme data from a PowerPoint template and writes a manifest JSON file.

**Example**

```bash
agent-slides learn corporate-template.pptx -o corporate-template.manifest.json
```

**Example stderr**

```text
Warning: layout 'Comparison Lab': skipped unsupported chart placeholder 'Content Placeholder 3'
Warning: layout 'Comparison Lab': skipped unsupported media_clip placeholder 'Content Placeholder 5'
Warning: layout 'Captioned Content': skipped unsupported table placeholder 'Content Placeholder 2'
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "source": "corporate-template.pptx",
    "layouts_found": 11,
    "usable_layouts": 11
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the input PPTX does not exist.
- `SCHEMA_ERROR` when the file is not a valid PPTX or is password-protected.
- `SCHEMA_ERROR` when the manifest output cannot be written.

### `inspect`

**Synopsis**

```bash
agent-slides inspect MANIFEST.json
```

**Description**

Summarizes a learned manifest into a layout inventory with slot names and a `usable` flag for each layout.

**Example**

```bash
agent-slides inspect corporate-template.manifest.json
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "source": "corporate-template.pptx",
    "layouts_found": 11,
    "usable_layouts": 11,
    "theme_extracted": true,
    "layouts": [
      {
        "name": "Title Slide",
        "slug": "title_slide",
        "slots": ["heading", "subheading"],
        "usable": true
      },
      {
        "name": "Agenda",
        "slug": "agenda",
        "slots": ["heading", "body"],
        "usable": true
      }
    ]
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the manifest file does not exist.
- `SCHEMA_ERROR` when the manifest is not valid JSON or is missing required fields.

### `theme list`

**Synopsis**

```bash
agent-slides theme list
```

**Description**

Lists the built-in themes bundled with the package.

**Example**

```bash
agent-slides theme list
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "themes": ["academic", "corporate", "dark", "default", "startup"]
  }
}
```

**Error cases**

- None in normal use. If packaged theme assets are missing or corrupted, subsequent theme-loading commands will surface `THEME_NOT_FOUND` or `THEME_INVALID`.

### `theme apply`

**Synopsis**

```bash
agent-slides theme apply PATH --theme THEME
```

**Description**

Changes the theme recorded on an existing deck. This updates the sidecar and leaves slide content intact.

**Example**

```bash
agent-slides theme apply demo.json --theme corporate
```

**Example stdout**

```json
{
  "ok": true,
  "data": {
    "theme": "corporate",
    "previous": "default"
  }
}
```

**Error cases**

- `THEME_NOT_FOUND` when the selected theme does not exist.
- `THEME_INVALID` when the selected theme file is malformed.
- `FILE_NOT_FOUND` when the deck file does not exist.

### `preview`

**Synopsis**

```bash
agent-slides preview PATH [--port PORT] [--no-open]
```

**Description**

Starts the live preview HTTP and WebSocket server for a deck. The command runs until interrupted.

**Example**

```bash
agent-slides preview demo.json --port 8876 --no-open
```

**Example stdout on startup**

```json
{
  "ok": true,
  "data": {
    "url": "http://localhost:8876",
    "watching": "demo.json"
  }
}
```

**Example stdout on shutdown**

```json
{
  "ok": true,
  "data": {
    "stopped": true
  }
}
```

**Error cases**

- `FILE_NOT_FOUND` when the deck file does not exist.
- `SCHEMA_ERROR` when the deck JSON cannot be parsed or validated.
- Non-domain startup failures such as an occupied port surface as runtime exceptions rather than the standard JSON error envelope.
