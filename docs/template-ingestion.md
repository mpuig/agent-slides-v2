# Template Ingestion

`agent-slides` can learn a PowerPoint template into a JSON manifest, initialize decks against that manifest, and build PPTX output by cloning the original template instead of drawing from the built-in grid layouts.

The current workflow is:

1. `learn` extracts a manifest from a `.pptx` template.
2. `inspect` summarizes the learned layouts and slots.
3. You optionally edit the manifest JSON.
4. `init --template` creates a deck that uses template-backed layouts.
5. `build` reflows from manifest bounds and writes a PPTX by cloning the template.

## `learn`

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run agent-slides learn brand-template.pptx
```

By default, the command writes `brand-template.manifest.json` next to the source PPTX. `-o/--output` writes to a different path, and the manifest `source` field is stored relative to that output path.

Success output is JSON on stdout:

```json
{
  "ok": true,
  "data": {
    "source": "brand-template.pptx",
    "layouts_found": 11,
    "usable_layouts": 11
  }
}
```

Warnings are printed to stderr as plain text lines prefixed with `Warning:`. Today that covers:

- Unsupported placeholder types that are skipped during extraction: chart, media clip, org chart, and table placeholders.
- A learned template with zero usable layouts: `template has 0 usable layouts`.

Hard failures are returned as structured CLI errors:

- Missing template file: `FILE_NOT_FOUND`
- Invalid or corrupt PPTX: `SCHEMA_ERROR` with `not a valid PPTX file`
- Password-protected Office file: `SCHEMA_ERROR` with `password-protected files not supported`
- Template with no slide layouts at all: `SCHEMA_ERROR` with `template has no slide layouts`
- Theme extraction failures: `SCHEMA_ERROR` if required theme colors or fonts cannot be read

### What `learn` extracts

For every slide master and every layout under that master, `learn` records:

- `master_index` and layout `index`
- layout `name`
- a unique layout `slug`
- `usable`
- typed `placeholders`
- heuristic `slot_mapping`

It also extracts theme metadata:

- colors: `primary`, `secondary`, `accent`, `text`, `heading_text`, `subtle_text`, `background`
- fonts: `heading`, `body`
- spacing: `base_unit`, `margin`, `gutter`

All placeholder coordinates are stored in points, not EMU. The reader converts from PowerPoint EMU using `EMU_PER_POINT` and rounds to 3 decimals.

### Slot mapping heuristic

The learned manifest is opinionated. The current rules are:

- First `TITLE` placeholder by top/left position becomes `heading`.
- First `SUBTITLE` placeholder by top/left position becomes `subheading`.
- One `BODY` placeholder becomes `body`.
- Multiple `BODY` placeholders are sorted by top/left position first.
- If multiple body placeholders are on the same row, they become `col1`, `col2`, `col3`, ... from left to right.
- "Same row" currently means their `y` values differ by at most `54.0` points.
- If multiple body placeholders are not on the same row, only the first body placeholder becomes `body`.
- First `PICTURE` placeholder by top/left position becomes `image`.

Supported placeholder type normalization is:

- `TITLE`, `CENTER_TITLE`, `VERTICAL_TITLE` -> `TITLE`
- `SUBTITLE` -> `SUBTITLE`
- `BODY`, `OBJECT`, `VERTICAL_BODY`, `VERTICAL_OBJECT` -> `BODY`
- `PICTURE` -> `PICTURE`

Everything else is ignored, with warnings for chart/table/media/org-chart placeholders.

### Layout slugification and collisions

Layout slugs are generated from the layout name by:

- lowercasing
- replacing runs of non-`[a-z0-9]` characters with `_`
- trimming leading and trailing `_`
- falling back to `layout` if the result is empty

Slug collisions are resolved by suffixing `_2`, `_3`, and so on.

Examples:

- `Title Slide` -> `title_slide`
- second `Agenda` layout -> `agenda_2`

### Usable layout predicate

A learned layout is marked usable when either of these is true:

- it has at least one supported typed placeholder after extraction
- its layout name is `Blank` (case-insensitive)

If no learned layouts are usable, `learn` still writes the manifest and emits a warning.

## Manifest Format

The learned manifest written by `learn` has this shape:

```json
{
  "source": "brand-template.pptx",
  "source_hash": "8e4d2f0c7d5f4f4b6e89f7df4c7cb2d2fcb4b7f7a4d7b0d7e1d2d5a0c5c0c123",
  "slide_masters": [
    {
      "index": 0,
      "name": "Slide Master 1",
      "layouts": [
        {
          "index": 0,
          "master_index": 0,
          "name": "Title Slide",
          "slug": "title_slide",
          "usable": true,
          "placeholders": [
            {
              "idx": 0,
              "type": "TITLE",
              "name": "Title 1",
              "bounds": {
                "x": 36.0,
                "y": 24.0,
                "w": 648.0,
                "h": 84.0
              }
            },
            {
              "idx": 1,
              "type": "SUBTITLE",
              "name": "Subtitle 2",
              "bounds": {
                "x": 72.0,
                "y": 126.0,
                "w": 576.0,
                "h": 120.0
              }
            }
          ],
          "slot_mapping": {
            "heading": 0,
            "subheading": 1
          }
        },
        {
          "index": 3,
          "master_index": 0,
          "name": "Two Content",
          "slug": "two_content",
          "usable": true,
          "placeholders": [
            {
              "idx": 0,
              "type": "TITLE",
              "name": "Title 1",
              "bounds": {
                "x": 36.0,
                "y": 24.0,
                "w": 648.0,
                "h": 48.0
              }
            },
            {
              "idx": 1,
              "type": "BODY",
              "name": "Content Placeholder 2",
              "bounds": {
                "x": 36.0,
                "y": 126.0,
                "w": 300.0,
                "h": 356.375
              }
            },
            {
              "idx": 2,
              "type": "BODY",
              "name": "Content Placeholder 3",
              "bounds": {
                "x": 348.0,
                "y": 126.0,
                "w": 300.0,
                "h": 356.375
              }
            }
          ],
          "slot_mapping": {
            "heading": 0,
            "col1": 1,
            "col2": 2
          }
        }
      ]
    }
  ],
  "theme": {
    "colors": {
      "primary": "#112233",
      "secondary": "#445566",
      "accent": "#778899",
      "text": "#101010",
      "heading_text": "#202020",
      "subtle_text": "#E5E7EB",
      "background": "#FAFAFA"
    },
    "fonts": {
      "heading": "Aptos Display",
      "body": "Aptos"
    },
    "spacing": {
      "base_unit": 10.0,
      "margin": 60.0,
      "gutter": 20.0
    }
  }
}
```

Field notes:

- `source` is the template PPTX path relative to the manifest file.
- `source_hash` is the SHA-256 of the template at learn time.
- `slide_masters[].layouts[]` is the canonical learned representation.
- `slot_mapping` in learned manifests maps slot names to placeholder indices.
- `placeholders[].bounds` uses point units.
- `theme` is extracted from the template theme part, with spacing seeded from the built-in defaults.

### Registry-compatible `layouts` form

`TemplateLayoutRegistry` also accepts a flattened top-level `layouts` array or object for layout lookup and template reflow. This is useful for manual edits because you can replace an integer slot mapping with an object that carries explicit bounds and role metadata:

```json
{
  "source": "brand-template.pptx",
  "source_hash": "8e4d2f0c7d5f4f4b6e89f7df4c7cb2d2fcb4b7f7a4d7b0d7e1d2d5a0c5c0c123",
  "theme": {
    "colors": {
      "primary": "#112233"
    },
    "fonts": {
      "heading": "Aptos Display",
      "body": "Aptos"
    },
    "spacing": {
      "base_unit": 10.0,
      "margin": 60.0,
      "gutter": 20.0
    }
  },
  "layouts": [
    {
      "slug": "two_content",
      "usable": true,
      "slot_mapping": {
        "heading": {
          "role": "heading",
          "bounds": {
            "x": 36.0,
            "y": 24.0,
            "width": 648.0,
            "height": 48.0
          }
        },
        "col1": {
          "role": "body",
          "bounds": {
            "x": 36.0,
            "y": 126.0,
            "width": 300.0,
            "height": 356.375
          }
        }
      }
    }
  ]
}
```

Important caveat: the PPTX writer still needs `slide_masters[].layouts[]` with `master_index`, `index`, and integer placeholder bindings so it can reopen the real template layout. For full `learn -> init -> build` compatibility, edit the learned `slide_masters` structure in place and treat flattened `layouts` as a reflow convenience, not a replacement.

## Manual Manifest Editing

Manual editing is a first-class workflow:

1. `learn` the template.
2. `inspect` the result.
3. Edit the JSON.
4. `init --template` from the edited manifest.

`inspect` is useful because it shows `layouts_found`, `usable_layouts`, and the slot names inferred for each learned layout.

Common reasons to edit the manifest:

- rename ambiguous slots to match how you want to author content
- fix a body layout that should be `col1`/`col2` but was learned as a single `body`
- add explicit `role` metadata for a slot
- override bounds after inspecting a template with awkward placeholder geometry
- mark a layout unusable by setting `usable: false`

When you hand-edit slot mappings for template reflow, the registry accepts:

- integer placeholder references, as produced by `learn`
- object values with explicit `bounds`
- either `x`/`y`/`w`/`h` or `left`/`top`/`width`/`height`

Role inference for manual slot objects works like this:

- explicit `role` wins
- `type: "PICTURE"` becomes role `image`
- slot names like `heading`, `title`, `header` become role `heading`
- slot names like `subheading` and `subtitle` become role `body`
- slot names containing `image` or starting with `img` become role `image`
- otherwise the role defaults to `body`

## Template-Aware `init` and `build`

### `init --template`

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run agent-slides init deck.json --template brand-template.manifest.json
```

Current behavior:

- `--template` and `--theme` are mutually exclusive.
- `init` loads the manifest through `TemplateLayoutRegistry`.
- The deck theme is set to `registry.theme.name`.
- If the manifest theme has no explicit `name`, the registry derives one from the manifest filename as `extracted-<slug>`.
- `deck.template_manifest` is stored relative to the deck path, not as an absolute path.

### Template reflow

When a deck has `template_manifest`, the system switches from built-in grid reflow to `template_reflow`.

That changes the source of truth for computed geometry:

- built-in mode: positions come from built-in layout definitions and the grid engine
- template mode: positions come from manifest slot bounds

`template_reflow` currently:

- resolves the active `Theme` from the manifest
- looks up the template-backed `LayoutDef` from `TemplateLayoutRegistry`
- validates that each bound node references a defined slot
- validates that each slot has bounds
- computes text nodes with `fit_text()` using the default heading/body fitting rules
- computes image nodes from slot bounds directly

### Template-aware build

`build` does this for template-backed decks:

1. reads `deck.json`
2. resolves `deck.template_manifest` relative to the deck file
3. runs `template_reflow`
4. writes `deck.computed.json`
5. writes the output PPTX through the template-backed writer

The template-backed writer is intentionally different from the default writer:

1. load the manifest
2. resolve the original template PPTX from `source`
3. compare the live template hash with `source_hash`
4. open the template with `Presentation(template_path)`
5. delete all existing slides while keeping masters and layouts
6. add one slide per deck slide using the manifest `master_index` and layout `index`
7. fill native placeholders for bound text nodes
8. save the cloned presentation

Text filling is done by clearing the placeholder text frame and rebuilding paragraphs:

```python
text_frame = placeholder.text_frame
text_frame.clear()
text_frame.paragraphs[0].add_run().text = lines[0]
for line in lines[1:]:
    paragraph = text_frame.add_paragraph()
    paragraph.add_run().text = line
```

That is why template builds preserve native placeholder formatting from the source template: the writer does not assign font name or size on those runs.

### Hash verification

If the template file changed after `learn`, build still succeeds but emits a structured warning to stderr:

```json
{
  "warning": {
    "code": "TEMPLATE_CHANGED",
    "message": "Template source file changed since the manifest was learned."
  },
  "data": {
    "template": "/abs/path/to/brand-template.pptx",
    "expected_hash": "...",
    "actual_hash": "..."
  }
}
```

### Preview/build fidelity caveat

Preview and build share the same manifest-driven reflow, so slot bounds, theme colors, text fitting, and computed image placement line up.

They are not pixel-identical:

- preview renders computed nodes into HTML/SVG
- template build clones the actual PPTX layout and fills native placeholders
- the template-backed PPTX writer currently fills text placeholders only

So preview is faithful for layout geometry, but the final PPTX is the source of truth for native placeholder typography and any template-specific PowerPoint behavior.

## `TemplateLayoutRegistry`

`TemplateLayoutRegistry` lives in `agent_slides.model.template_layouts` and implements the same `LayoutProvider` protocol as the built-in layout registry.

It provides:

- `get_layout(slug)`
- `list_layouts()`
- `get_slot_names(slug)`
- `get_text_fitting(slug, role)`

It also exposes template-specific data used by reflow and build:

- `source_path`
- `source_hash`
- `theme`
- `get_layout_ref(slug)` for master/layout indices

The important architectural detail is that command code mostly does not branch on "template mode" versus "built-in mode". Instead, it asks `resolve_layout_provider(template_manifest)` for a provider:

- no manifest -> `BuiltinLayoutProvider`
- manifest present -> `TemplateLayoutRegistry`

That keeps mutations consistent across both modes:

- `mutate_deck()` always reads the deck, runs the semantic mutation, bumps the revision, reflows, and writes both sidecars
- template-backed decks swap in `template_reflow`
- built-in decks keep using the normal grid reflow

From the caller's perspective, commands like `slide add` and `slot set` work the same way in both modes. The difference is which layout provider and reflow engine sits underneath.
