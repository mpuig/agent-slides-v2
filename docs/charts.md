# Charts

`agent-slides` can write native editable PowerPoint chart objects for seven chart types:

- `bar`
- `column`
- `line`
- `pie`
- `scatter`
- `area`
- `doughnut`

Six of those are category charts and share one data model. `scatter` uses a different XY data model.

> [!WARNING]
> PowerPoint charts do not inherit the active `agent-slides` theme. If you care about chart colors, set `style.series_colors` explicitly in the chart payload.

## Supported chart types

| Chart type | Data model | PPTX renderer |
| --- | --- | --- |
| `bar` | Category chart | `CategoryChartData` |
| `column` | Category chart | `CategoryChartData` |
| `line` | Category chart | `CategoryChartData` |
| `pie` | Category chart | `CategoryChartData` |
| `area` | Category chart | `CategoryChartData` |
| `doughnut` | Category chart | `CategoryChartData` |
| `scatter` | XY scatter chart | `XyChartData` |

## ChartSpec format

Charts are stored on chart nodes as a `chart_spec` object:

```json
{
  "chart_type": "bar",
  "title": "Quarterly revenue",
  "categories": ["Q1", "Q2", "Q3"],
  "series": [
    {
      "name": "Revenue",
      "values": [12.0, 18.0, 24.0]
    }
  ],
  "style": {
    "has_legend": true,
    "has_data_labels": false,
    "series_colors": ["#FF6B35"]
  }
}
```

Fields:

- `chart_type`: one of `bar`, `column`, `line`, `pie`, `scatter`, `area`, `doughnut`
- `title`: optional chart title
- `categories`: required for category charts
- `series`: required for category charts
- `scatter_series`: required for `scatter`
- `style.has_legend`: optional, defaults to `true`
- `style.has_data_labels`: optional, defaults to `false`
- `style.series_colors`: optional list of `#RRGGBB` or `RRGGBB` colors

### Category chart payload

Category charts use `categories` plus one or more named `series`:

```json
{
  "categories": ["Q1", "Q2", "Q3"],
  "series": [
    {
      "name": "Revenue",
      "values": [12.0, 18.0, 24.0]
    },
    {
      "name": "Cost",
      "values": [7.0, 9.0, 10.0]
    }
  ],
  "style": {
    "has_legend": true,
    "series_colors": ["#FF6B35", "#004E89"]
  }
}
```

### Scatter payload

Scatter charts use `scatter_series`, and each series holds explicit `x`/`y` points:

```json
{
  "scatter_series": [
    {
      "name": "Observed",
      "points": [
        { "x": 0.7, "y": 2.7 },
        { "x": 1.8, "y": 3.2 },
        { "x": 2.6, "y": 0.8 }
      ]
    },
    {
      "name": "Projected",
      "points": [
        { "x": 1.3, "y": 3.7 },
        { "x": 2.7, "y": 2.3 },
        { "x": 1.6, "y": 1.8 }
      ]
    }
  ],
  "style": {
    "has_legend": false,
    "series_colors": ["#AA0000", "#0055CC"]
  }
}
```

## Examples By Chart Type

### `bar`

```json
{
  "categories": ["Q1", "Q2", "Q3"],
  "series": [{ "name": "Revenue", "values": [12.0, 18.0, 16.0] }]
}
```

### `column`

```json
{
  "categories": ["Q1", "Q2", "Q3"],
  "series": [{ "name": "Revenue", "values": [8.0, 13.0, 21.0] }]
}
```

### `line`

```json
{
  "categories": ["Jan", "Feb", "Mar"],
  "series": [
    { "name": "Plan", "values": [10.0, 11.0, 12.0] },
    { "name": "Actual", "values": [9.5, 12.0, 13.5] }
  ]
}
```

### `pie`

```json
{
  "categories": ["North", "South", "West"],
  "series": [{ "name": "Share", "values": [55.0, 30.0, 15.0] }]
}
```

### `scatter`

```json
{
  "scatter_series": [
    {
      "name": "Observations",
      "points": [
        { "x": 1.0, "y": 2.5 },
        { "x": 2.5, "y": 3.75 },
        { "x": 4.0, "y": 5.25 }
      ]
    }
  ]
}
```

### `area`

```json
{
  "categories": ["Q1", "Q2", "Q3"],
  "series": [{ "name": "Pipeline", "values": [18.0, 16.0, 22.0] }]
}
```

### `doughnut`

```json
{
  "categories": ["Product A", "Product B", "Product C"],
  "series": [{ "name": "Mix", "values": [40.0, 35.0, 25.0] }]
}
```

## CLI usage

### `chart add`

Use exactly one of `--data` or `--data-file`.

Inline JSON:

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type bar \
  --title "Revenue by quarter" \
  --data '{"categories":["Q1","Q2","Q3"],"series":[{"name":"Revenue","values":[12,18,24]}],"style":{"series_colors":["#FF6B35"]}}'
```

JSON file:

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type scatter \
  --data-file chart-data.json
```

`chart add` creates or replaces the node bound to the target slot and returns the chart node id in JSON output.

### `chart update`

Update an existing chart node by id:

```bash
agent-slides chart update deck.json \
  --node n-2 \
  --data '{"categories":["Q1","Q2","Q3"],"series":[{"name":"Revenue","values":[20,24,30]}]}'
```

The `--data` payload uses the same shape as `chart_spec`. In practice, this is most useful for replacing categories, series, scatter points, style, or title while keeping the same node id.

### Batch support

The `batch` command accepts `chart_add` and `chart_update` operations in JSON stdin:

```json
[
  { "command": "slide_add", "args": { "layout": "two_col" } },
  {
    "command": "chart_add",
    "args": {
      "slide": 0,
      "slot": "left",
      "type": "bar",
      "data": {
        "categories": ["Q1", "Q2"],
        "series": [{ "name": "Revenue", "values": [9.0, 11.0] }]
      }
    }
  },
  {
    "command": "chart_update",
    "args": {
      "node": "n-2",
      "data": {
        "categories": ["Q1", "Q2", "Q3"],
        "series": [{ "name": "Revenue", "values": [9.0, 11.0, 13.0] }]
      }
    }
  }
]
```

Example:

```bash
cat ops.json | agent-slides batch deck.json
```

## PPTX rendering

Charts are written as native editable PowerPoint chart objects, not flattened images.

- Category charts are rendered through `python-pptx` `CategoryChartData`.
- Scatter charts are rendered through `python-pptx` `XyChartData`.
- The output chart type maps directly to the PowerPoint chart object (`BAR_CLUSTERED`, `COLUMN_CLUSTERED`, `LINE`, `PIE`, `AREA`, `DOUGHNUT`, `XY_SCATTER`).

### Theming gotcha

This is the main behavior to remember for production decks:

- text and shapes inherit the active `agent-slides` theme
- charts do not inherit that theme
- if `style.series_colors` is omitted, PowerPoint uses its own default chart palette

If you need predictable deck-wide chart colors, set `style.series_colors` on every chart payload.

### ChartStyle behavior

- `has_legend` is applied to the PowerPoint chart object
- `series_colors` is applied to chart series fills
- `has_data_labels` is part of the chart schema, but the current PPTX writer does not apply it yet

## Validation rules

Hard validation:

- Category charts require both `categories` and `series`
- Scatter charts require `scatter_series` and reject `categories` / `series`
- Category charts reject `scatter_series`
- Every category-chart series must have the same number of `values` as there are `categories`
- Pie charts support exactly one series
- `series_colors` entries must use `#RRGGBB` or `RRGGBB`

Warnings:

- More than 10 series is accepted, but emits a readability warning
- Pie charts with negative values are accepted, but PowerPoint may render them unexpectedly

## Limitations

- No gantt, calendar, timeline, flow-diagram, or other non-chart visualization types
- No combo charts
- No 3D chart variants
- Preview is approximate only, not the native PowerPoint chart renderer
- The current preview draws lightweight SVG previews for `bar`, `column`, and `line`; other chart types fall back to a generic chart placeholder card
- `style.has_data_labels` is accepted in chart JSON but is not yet applied by the PPTX writer
