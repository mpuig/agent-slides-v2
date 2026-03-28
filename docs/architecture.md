# agent-slides Architecture

This document describes the current checked-in architecture of `agent-slides`. It is intentionally code-first: the source of truth is the implementation under `src/agent_slides/` and the behavioral contract in `tests/`.

## File Map

- `src/agent_slides/model/types.py`: scene graph types, computed types, counters, revision model
- `src/agent_slides/model/layouts.py`: built-in layout registry and grid definitions
- `src/agent_slides/model/layout_provider.py`: `LayoutProvider`, built-in provider, template-provider resolution
- `src/agent_slides/model/template_layouts.py`: manifest-backed layout loading
- `src/agent_slides/model/themes.py`: theme loading and semantic role to concrete style resolution
- `src/agent_slides/commands/mutations.py`: mutation dispatch and slot alias handling
- `src/agent_slides/io/sidecar.py`: read/write helpers, computed sidecar handling, mutation pipeline
- `src/agent_slides/engine/reflow.py`: built-in grid reflow
- `src/agent_slides/engine/template_reflow.py`: manifest-bounds reflow for template decks
- `src/agent_slides/engine/text_fit.py`: text-fitting heuristics
- `src/agent_slides/io/pptx_writer.py`: PowerPoint writer
- `src/agent_slides/commands/build.py`: build path that reflows, persists computed state, and writes `.pptx`
- `src/agent_slides/preview/server.py` and `src/agent_slides/preview/watcher.py`: preview transport and file watching

## 1. Scene Graph Model

The authoring model is a small scene graph stored in `deck.json`.

```text
Deck
|- deck_id
|- revision
|- theme
|- design_rules
|- template_manifest?
|- _counters
|  |- slides
|  `- nodes
`- slides[]
   `- Slide
      |- slide_id
      |- layout
      |- nodes[]
      |  `- Node
      |     |- node_id
      |     |- slot_binding?
      |     |- type: text | image | chart
      |     |- content: NodeContent(TextBlock[])
      |     |- image_path?
      |     |- image_fit
      |     |- chart_spec?
      |     `- style_overrides
      `- computed{node_id -> ComputedNode}
```

### Core types

- `Deck` owns the slide list, the active theme, an optional `template_manifest`, a `revision`, and `_counters` (`Counters`) for stable ID generation.
- `Slide` is a semantic slide definition: `slide_id`, `layout`, `nodes`, and in-memory `computed`.
- `Node` is the authoring-level content unit. `Node.type` is one of `"text"`, `"image"`, or `"chart"`.
- `ComputedNode` is derived state: resolved geometry (`x`, `y`, `width`, `height`), resolved styling (`font_family`, `color`, `bg_color`, `font_bold`, `image_fit`), overflow state, and the deck revision that produced it.

### Node payload rules

`src/agent_slides/model/types.py` enforces type-specific constraints:

- Text nodes store text in `Node.content`, which is a `NodeContent` wrapper around `TextBlock[]`.
- Image nodes use `image_path` and must not carry non-empty text content unless they are image placeholders with `style_overrides["placeholder"] == True`.
- Chart nodes use `chart_spec: ChartSpec` and must not define `image_path`.

`NodeContent` is the canonical text model. A block is one of:

- `paragraph`
- `bullet`
- `heading`

Legacy string content is still accepted and coerced into `NodeContent`; see `docs/decisions/0001-structured-text-model.md`.

### Stable IDs and revisioning

- `Deck.next_slide_id()` increments `_counters.slides` and returns `s-<n>`.
- `Deck.next_node_id()` increments `_counters.nodes` and returns `n-<n>`.
- `Deck.bump_revision()` increments the deck revision before reflow and write.

The current optimistic-lock boundary is the deck revision. `write_deck()` in `src/agent_slides/io/sidecar.py` reloads the deck from disk and rejects the write if the persisted revision no longer matches the caller's `expected_revision`.

## 2. Two-File Strategy

The repository uses two persisted JSON files:

- `deck.json`: authoring source of truth
- `deck.computed.json`: derived layout cache

### Source vs derived state

`src/agent_slides/io/sidecar.py` serializes them separately:

- `_serialize_deck_payload(deck)` drops `slide.computed` before writing `deck.json`
- `_serialize_computed_payload(deck)` writes `ComputedDeck.from_deck(deck)` into `deck.computed.json`

`ComputedDeck` and `ComputedSlide` live in `src/agent_slides/model/types.py`. They only carry:

- `deck_id`
- `revision`
- per-slide computed node maps

### Read path

`read_deck(path)`:

1. parses `deck.json`
2. validates it as `Deck`
3. tries to read `deck.computed.json`
4. applies computed data only when `deck_id` and `revision` match

That last rule prevents stale computed state from becoming authoritative.

### Write path

`_write_bundle_atomic()` stages both files as `.tmp` files, then renames them in order:

```text
deck.json.tmp           -> deck.json
deck.computed.json.tmp  -> deck.computed.json
```

This is not a single cross-file transaction, but it does preserve the intended ordering: source first, computed second.

### Preview consumption

The historical design note in `CLAUDE.md` describes `deck.computed.json` as the watch boundary. The current implementation is slightly different:

- `PreviewServer` in `src/agent_slides/preview/server.py` constructs `SidecarWatcher` with the deck path from `preview.py`
- `SidecarWatcher` in `src/agent_slides/preview/watcher.py` watches that `deck.json` path
- on change, it calls `read_deck()`, which merges `deck.computed.json` when revisions match

So the two-file contract is still real, but the current live preview watches `deck.json` and reloads computed state through the shared read path rather than watching `deck.computed.json` directly.

## 3. Mutation Pipeline

All semantic deck edits are supposed to go through `mutate_deck()` in `src/agent_slides/io/sidecar.py`.

```text
CLI / preview tool / batch op
        |
        v
apply_mutation(deck, command, args, provider)
        |
        v
mutate_deck(path, fn)
        |
        +--> read_deck(path)
        +--> resolve_layout_provider(resolve_manifest_path(path, deck))
        +--> fn(deck, provider)
        +--> deck.bump_revision()
        +--> reflow_deck(...) or template_reflow(...)
        `--> write_deck(path, deck, expected_revision)
                 |
                 `--> write deck.json, then deck.computed.json
```

### `mutate_deck(path, fn)`

`mutate_deck()` performs the shared pipeline:

1. `read_deck(path)`
2. resolve the active `LayoutProvider`
3. remember the pre-mutation revision
4. run the caller callback against the in-memory `Deck`
5. bump `Deck.revision`
6. reflow with either:
   - `reflow_deck()` for built-in layouts
   - `template_reflow()` for template-backed layouts
7. persist through `write_deck()`, which performs the optimistic-lock check

That is the main architectural guardrail. CLI wrappers in `src/agent_slides/commands/slide.py`, `slot.py`, `chart.py`, `theme.py`, and `batch.py` delegate to it instead of open-coding read/write/reflow.

### `apply_mutation(deck, command, args, provider)`

`src/agent_slides/commands/mutations.py` contains a single mutation dispatcher for the semantic operations. The currently supported commands are:

- `slide_add`
- `slide_remove`
- `slide_set_layout`
- `slot_set`
- `slot_clear`
- `slot_bind`
- `chart_add`
- `chart_update`

These names are also collected in `SUPPORTED_MUTATION_COMMANDS`.

### Slot alias resolution

`SLOT_ALIASES` currently normalizes a few common user-facing names:

- `title -> heading`
- `subtitle -> subheading`
- `left -> col1`
- `right -> col2`

`_resolve_slot_name()` applies those aliases and then validates the result against the active layout definition.

### Mutation responsibilities

`apply_mutation()` is responsible for semantic changes only:

- creating/removing slides
- rebinding slots
- coercing text/image/chart payloads
- creating placeholder nodes for layouts
- generating stable IDs through `Deck.next_slide_id()` / `Deck.next_node_id()`

It does not compute geometry. Reflow happens after the mutation callback returns.

## 4. LayoutProvider Protocol

The reflow and mutation layers do not talk directly to `LAYOUTS`; they talk to a provider protocol in `src/agent_slides/model/layout_provider.py`.

```python
class LayoutProvider(Protocol):
    def get_layout(self, slug: str) -> LayoutDef: ...
    def list_layouts(self) -> list[str]: ...
    def get_slot_names(self, slug: str) -> list[str]: ...
    def get_text_fitting(self, slug: str, role: str) -> TextFitting: ...
```

### Built-in provider

`BuiltinLayoutProvider` is a thin wrapper around the helpers in `src/agent_slides/model/layouts.py`:

- `get_layout()`
- `list_layouts()`
- `get_slot_names()`
- `get_text_fitting()`

This keeps built-in layouts behind the same interface as template-derived ones.

### Template provider

`TemplateLayoutRegistry` in `src/agent_slides/model/template_layouts.py` loads a learned manifest JSON and exposes the same protocol. It also carries template-specific metadata:

- `source_path`
- `source_hash`
- `theme`
- layout refs for PPTX/template mapping

When it loads a manifest, it:

- coerces manifest layout entries from either `layouts` or `slide_masters[*].layouts`
- turns placeholder bounds into `SlotDef` objects with absolute `x/y/width/height`
- infers missing slot roles from slot names or placeholder types
- synthesizes text-fitting defaults for non-image roles

### Provider resolution

`resolve_layout_provider(template_manifest)` decides which provider to use:

- `None` -> `BuiltinLayoutProvider()`
- non-empty manifest path -> `TemplateLayoutRegistry(template_manifest)`

`resolve_manifest_path(deck_path, deck)` in `src/agent_slides/io/sidecar.py` converts `Deck.template_manifest` into an absolute path relative to the deck file before that resolution happens.

## 5. Reflow Engine

The reflow layer turns semantic slides and slots into `ComputedNode` records.

```text
slide.layout
   |
   v
LayoutProvider.get_layout(slide.layout)
   |
   v
for each bound node
   |
   +--> resolve slot frame
   |     |- built-in layout: derive from grid, theme margin, gutter
   |     `- template layout: use manifest placeholder bounds
   |
   +--> resolve semantic style
   |     `- resolve_style(theme, slot.role)
   |
   `--> dispatch by node type / slot role
         |- text  -> fit_text(...) -> ComputedNode(content_type="text")
         |- image -> preserve frame -> ComputedNode(content_type="image")
         `- chart -> preserve frame -> ComputedNode(content_type="chart")
```

### Built-in grid reflow

`src/agent_slides/engine/reflow.py` handles built-in layouts.

The key steps are:

1. load the active `LayoutDef`
2. compute slot bounds from `GridDef`
3. resolve typography and colors from the active theme
4. branch by node type

Grid positioning comes from:

- `layout.grid.row_heights`
- `layout.grid.col_widths`
- theme spacing (`margin`, `gutter`)
- `SlotDef.grid_row` / `SlotDef.grid_col`

Full-bleed slots zero out margin and gutter during frame calculation.

### Text fitting

`src/agent_slides/engine/text_fit.py` uses a heuristic fitter:

- average character width is approximated as `0.6 * font_size`
- line height is approximated from block type
- headings get a `1.35x` font-size multiplier
- bullets subtract indentation width from the available line width
- block spacing adds vertical cost between `TextBlock`s
- font size shrinks in `2pt` steps (`SHRINK_STEP_PT = 2.0`) until the content fits or `min_size` is reached

Built-in default fitting lives in `src/agent_slides/model/layouts.py`:

- heading: `32pt` down to `24pt`
- body: `18pt` down to `10pt`

### Style resolution

`src/agent_slides/model/themes.py` maps semantic slot roles to concrete style:

- `heading` -> heading font, heading color, bold
- `body` and `quote` -> body font, main text color
- `attribution` -> body font, subtle text color
- `image` -> body font and text color defaults, mostly relevant for unified computed payloads

### Built-in reflow dispatch

`reflow.py` has an explicit three-way branch:

- chart nodes get geometry only, no text fitting, and `content_type="chart"`
- image nodes, or any node occupying an image slot, get geometry only and `content_type="image"`
- text nodes get `fit_text(...)` and `content_type="text"`

For full-bleed image slots, `contain` is upgraded to `stretch` in computed output so downstream renderers fill the slide.

### Template reflow

`src/agent_slides/engine/template_reflow.py` skips the grid math and uses placeholder bounds from the manifest-backed `TemplateLayoutRegistry`.

It still:

- resolves style from the manifest-derived theme
- uses `registry.get_text_fitting(...)` for text
- emits `ComputedNode` records per bound node

One current implementation detail matters: template reflow has explicit branches for image and text, but not a dedicated chart branch. The built-in reflow path is three-way; the template reflow path is currently two-way.

## 6. PPTX Writer

`src/agent_slides/io/pptx_writer.py` contains two write paths selected by `write_pptx(deck, output_path, ...)`.

### A. From-scratch writer

If `deck.template_manifest` is unset, `write_pptx()` calls `_write_v0_pptx()`.

That path:

1. creates a new `Presentation()`
2. sets slide size to 10 x 7.5 inches
3. creates blank slides
4. renders each bound node from `slide.computed`

Rendering dispatch is explicit:

- text -> `_render_text_node()` -> `SlideShapes.add_textbox(...)`
- image -> `_render_image_node()` -> `SlideShapes.add_picture(...)`
- chart -> `_render_chart_node()` -> `SlideShapes.add_chart(...)`

Important details:

- text rendering translates `TextBlock`s into paragraphs and runs
- heading blocks scale font size by `1.35x`
- image rendering applies `contain`, `cover`, or `stretch` through `_fit_image_to_slot()`
- chart rendering uses native editable PowerPoint chart objects:
  - category charts use `CategoryChartData`
  - scatter charts use `XyChartData`
  - chart types map through `CHART_TYPE_MAP`

### B. Template-backed writer

If `deck.template_manifest` is set, `write_pptx()` calls `_write_template_pptx()`.

That path uses a second template-reader type defined inside `src/agent_slides/io/pptx_writer.py`:

- it reads manifest metadata needed for slide master/layout binding
- it resolves the source template `.pptx`
- it warns to stderr if the template hash no longer matches the manifest

The actual write flow is:

```text
Presentation(template.pptx)
    |
    +--> delete all existing slides
    +--> for each deck slide:
    |      +--> resolve learned master/layout binding
    |      +--> add a slide from that native PowerPoint layout
    |      `--> fill mapped placeholders
    `--> save(output_path)
```

Placeholder filling is text-only today:

- `_fill_placeholder()` only handles nodes where `node.type == "text"`
- it calls `TextFrame.clear()`
- it writes one run for the first line and additional paragraphs for later lines

So the current template-backed PPTX writer preserves native slide layouts and native text placeholders, but it does not render image or chart nodes into template decks yet.

## Related Build Path

The `build` command in `src/agent_slides/commands/build.py` is the non-mutating output pipeline:

1. `read_deck(path)`
2. resolve the active layout provider
3. run `reflow_deck()` or `template_reflow()`
4. `write_computed_deck(path, deck)`
5. `write_pptx(deck, output_path, asset_base_dir=path.parent)`

That keeps build output aligned with the same computed state model used by mutation and preview.
