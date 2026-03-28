# Preview Server

`agent-slides preview` runs a thin live-preview stack on top of the persisted deck files. It serves a browser client over HTTP, pushes change notifications over WebSocket, and reloads deck state from disk instead of re-running layout inside the browser.

## Server Architecture

The preview server uses a single `websockets` server instance for both HTTP responses and WebSocket upgrades. `PreviewServer.start()` calls `serve(..., process_request=...)`, so the same host and port handle the HTML client, JSON/image endpoints, and `/ws`.

```text
agent-slides preview deck.json
        |
        v
_ForegroundPreviewServer
        |
        v
 PreviewServer(host, port)
        |
        +--> HTTP `/` and `/client.html` -> packaged `client.html`
        +--> HTTP `/api/deck`           -> JSON from `load_deck_payload()`
        +--> HTTP `/api/images/<path>`  -> image bytes relative to deck dir
        +--> WebSocket `/ws`            -> live `deck.updated` messages
        |
        `--> SidecarWatcher(deck.json)
                 |
                 +--> debounce filesystem events (50 ms default)
                 `--> reload with `read_deck()`
                          |
                          +--> read `deck.json`
                          `--> merge `deck.computed.json` when revision matches
```

Key implementation details:

- HTTP and WebSocket traffic share one port.
- The preview client connects to `/ws`.
- The watcher debounces rapid successive filesystem events before reloading.
- On macOS, the watcher uses `PollingObserver`; other platforms use the default `Observer`.

### Current Watch Target

The architectural contract around computed sidecars is still real, but the current shipped preview implementation watches `deck.json`, not `deck.computed.json`.

- `PreviewServer` constructs `SidecarWatcher` with the path passed to `agent-slides preview`.
- `SidecarWatcher.load_deck_payload()` calls `read_deck(path)`.
- `read_deck()` loads `deck.json`, then loads `deck.computed.json` and applies computed nodes only when `deck_id` and `revision` match.

That means the preview currently treats `deck.json` as the filesystem trigger and `deck.computed.json` as optional derived state merged during reload.

## SVG Rendering

The packaged browser client is [`src/agent_slides/preview/client.html`](/Users/puigmarc/code/agent-slides-v2-workspaces/mpuig_agent-slides-v2_117/src/agent_slides/preview/client.html). On load it fetches `/api/deck`, renders the current slide, and then opens a WebSocket to `/ws` for live updates.

The slide surface is a single SVG:

```html
<svg id="stage" viewBox="0 0 720 540" role="img" aria-label="Slide preview"></svg>
```

`720x540` matches a `10" x 7.5"` slide at `72 pt/in`, so preview coordinates line up with the same point-based geometry used by reflow and PPTX generation.

### Text Nodes

`renderTextNode()` draws text directly into SVG from computed geometry and resolved text styles.

- optional background fill is rendered as an SVG `<rect>`
- text wrapping is approximated in the browser with canvas text measurement
- structured content blocks are flattened into lines, including bullet prefixes and indentation levels
- font family, font size, bold weight, color, and bounding box come from computed node state

### Image Nodes

`renderImageNode()` emits an SVG `<image>` pointing at `/api/images/<relative path>`.

- image bytes are served from the deck directory by `PreviewServer._read_image_bytes()`
- `computed.image_fit` maps to SVG `preserveAspectRatio`
- `contain` becomes `xMidYMid meet`
- `cover` becomes `xMidYMid slice`
- `stretch` becomes `none`

### Chart Nodes

`renderChartNode()` renders a preview card inside SVG rather than a native PowerPoint chart object.

- bar charts get a horizontal bar approximation
- column charts get a grouped-column approximation
- line charts get a polyline approximation
- unsupported chart types, including scatter, fall back to a generic "Preview approximation" panel

The chart preview also renders a title and a data summary derived from `chart_spec`.

### Fidelity Caveat

The preview is intentionally approximate. PPTX output remains authoritative for:

- final PowerPoint text layout and wrapping
- native chart rendering and editing behavior
- any rendering differences between browser SVG and PowerPoint

The browser preview is for fast iteration, not a byte-for-byte PowerPoint renderer.

## Preview Command

The user-facing entry point is:

```bash
agent-slides preview deck.json [--port PORT] [--no-open]
```

Behavior in the current CLI:

- validates the input path with `read_deck()`
- starts `PreviewServer` on `localhost` and the requested port
- opens the browser unless `--no-open` is set
- prints a JSON success payload with the preview URL
- runs until `Ctrl+C`
- stops the server and prints a final JSON payload with `"stopped": true`

## Two-File Strategy

Deck mutation and preview rely on the write order between source and computed files.

1. `mutate_deck()` reads `deck.json`
2. it applies semantic changes
3. it bumps `Deck.revision`
4. it reflows the full deck
5. it writes `deck.json`
6. it writes `deck.computed.json`

Both files are staged through `*.tmp` paths and renamed into place, but they are still two separate filesystem updates. That is why the ordering matters.

### Why The Ordering Matters

- `deck.json` remains the authoring source of truth
- `deck.computed.json` is derived state consumed by preview and other downstream readers
- a reader can briefly observe the new source file before the new computed file lands

The stale-read guard is the revision match in `ComputedDeck.apply_to_deck()`:

- if `deck_id` differs, computed state is ignored
- if `revision` differs, computed state is ignored

So even though the preview can momentarily read a newer `deck.json` with an older `deck.computed.json`, it will not attach stale computed geometry to the deck object.

### Preview Implication

The design intent described in the decision docs is to watch `deck.computed.json` as the "reflow finished" signal. The current live implementation has not taken that last step yet:

- watcher trigger today: `deck.json` change
- computed merge today: happens during `read_deck()`
- stale-read protection today: `deck_id` and `revision` matching
- burst protection today: debounce in `SidecarWatcher`

That combination is what ships now, and it is the behavior this document describes.
