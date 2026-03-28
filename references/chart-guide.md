# Chart Guide

Choose the chart from the argument first, then fit the data to that argument. If the story is unclear, fix the story before you pick a chart.

## Chart Selection Table

| Data relationship | Chart type | `agent-slides` type | When to use |
| --- | --- | --- | --- |
| Trend over time | Line | `line` | Show growth, decline, inflection points, or plan-vs-actual over ordered periods. |
| Comparison across categories | Clustered column | `column` | Compare a small number of categories when labels are short and vertical bars are easy to scan. |
| Ranking or comparison with long labels | Horizontal bar | `bar` | Compare items with long category names or when sorted rank order matters most. |
| Magnitude over time | Area | `area` | Show how totals rise or fall over time when the filled shape helps emphasize size, not just direction. |
| Part-to-whole | Pie | `pie` | Show composition for 3 to 6 segments when one slice is clearly dominant. |
| Part-to-whole with a center callout | Doughnut | `doughnut` | Same use case as pie, but better when the center hole can hold a headline metric. |
| Correlation | Scatter | `scatter` | Show the relationship between two numeric variables, clusters, or outliers. |

`agent-slides` currently supports `bar`, `column`, `line`, `pie`, `scatter`, `area`, and `doughnut`. It does not currently expose stacked, combo, or 3D chart variants. If you think you need a stacked bar for composition over time, first ask whether `area` or a grouped `bar`/`column` chart makes the argument more clearly with the current CLI.

## Formatting Rules

1. Write an action title that states the takeaway: "Enterprise pipeline doubled in Q3", not "Pipeline by quarter".
2. Remove chart junk: unnecessary gridlines, borders, shadows, 3D styling, and decorative backgrounds.
3. Label the data as directly as possible so the audience does not have to bounce between marks and legend.
4. Keep one chart per slide unless two views are required to answer the same question.
5. Round numbers to business-scale units such as `$2.5B`, `42%`, or `1.3x`.
6. Sort bars from largest to smallest unless the category order is chronological or otherwise fixed.
7. Use color intentionally: reserve the accent color for the point you want the reader to remember, and keep comparison series neutral.

## Common Pitfalls

| Pitfall | Why it hurts | Fix |
| --- | --- | --- |
| Too many pie or doughnut segments | Small slices are hard to compare and labels become unreadable. | Keep composition charts to 3 to 6 segments. Group the tail into "Other" or switch to a sorted `bar` chart. |
| Overlapping data labels | The key numbers become harder to read than the chart itself. | Reduce label count, round values, shorten category names, or switch to a simpler chart type. |
| Missing annotation for the key insight | The audience must infer the point on its own. | Add an action title plus a short callout on the outlier, inflection point, or winning category. |
| Wrong chart for the relationship | The visual answers the wrong question, even if the data is accurate. | Map the argument to the selection table first, then shape the data payload to match that chart. |
| Asking for stacked output from `bar` | The current CLI writes clustered PowerPoint bar charts, not stacked ones. | Use `area` for composition-over-time stories, or plan for manual PowerPoint restyling after export. |
| Expecting `series_colors` to highlight one bar inside a single-series chart | `series_colors` applies to chart series fills, not individual points. | Use it to emphasize one series against neutral peers. If the argument hinges on one category, consider a two-series framing or annotate the key bar directly. |

## Integration With `agent-slides`

### CLI mapping

- Use `agent-slides chart add ... --type line` for trend stories.
- Use `agent-slides chart add ... --type column` for category comparison with short labels.
- Use `agent-slides chart add ... --type bar` for rankings and long-label comparisons.
- Use `agent-slides chart add ... --type area` for magnitude-over-time stories.
- Use `agent-slides chart add ... --type pie` for simple composition.
- Use `agent-slides chart add ... --type doughnut` for simple composition with a center callout.
- Use `agent-slides chart add ... --type scatter` for XY relationships.

### Data format examples

#### `line`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type line \
  --title "Conversion improved after the pricing change" \
  --data '{
    "categories": ["Jan", "Feb", "Mar", "Apr"],
    "series": [
      {"name": "Conversion", "values": [3.1, 3.4, 4.2, 4.8]}
    ]
  }'
```

#### `column`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type column \
  --title "Enterprise leads more pipeline than any other segment" \
  --data '{
    "categories": ["SMB", "Mid-market", "Enterprise"],
    "series": [
      {"name": "Pipeline ($M)", "values": [18, 27, 41]}
    ]
  }'
```

#### `bar`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type bar \
  --title "North America is the largest region" \
  --data '{
    "categories": ["North America", "Europe", "APAC", "LATAM"],
    "series": [
      {"name": "Revenue ($M)", "values": [84, 62, 47, 19]}
    ]
  }'
```

Sort ranking bars in the payload order you want to show on the slide.

#### `area`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type area \
  --title "Open pipeline reached a new high in Q4" \
  --data '{
    "categories": ["Q1", "Q2", "Q3", "Q4"],
    "series": [
      {"name": "Open pipeline ($M)", "values": [32, 38, 45, 57]}
    ]
  }'
```

#### `pie`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type pie \
  --title "Services are now most of the revenue mix" \
  --data '{
    "categories": ["Services", "Software", "Support"],
    "series": [
      {"name": "Revenue share", "values": [52, 31, 17]}
    ]
  }'
```

#### `doughnut`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type doughnut \
  --title "Renewal revenue drives most ARR" \
  --data '{
    "categories": ["Renewal", "Expansion", "New logo"],
    "series": [
      {"name": "ARR mix", "values": [61, 24, 15]}
    ]
  }'
```

#### `scatter`

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type scatter \
  --title "Higher activation predicts better retention" \
  --data '{
    "scatter_series": [
      {
        "name": "Accounts",
        "points": [
          {"x": 18, "y": 62},
          {"x": 26, "y": 71},
          {"x": 34, "y": 79},
          {"x": 41, "y": 86}
        ]
      }
    ]
  }'
```

### `series_colors` guidance

Use `style.series_colors` when the chart has multiple series and one series deserves emphasis.

```bash
agent-slides chart add deck.json \
  --slide 0 \
  --slot body \
  --type line \
  --title "Actual bookings pulled ahead of plan" \
  --data '{
    "categories": ["Jan", "Feb", "Mar", "Apr"],
    "series": [
      {"name": "Plan", "values": [12, 13, 14, 15]},
      {"name": "Actual", "values": [11, 14, 16, 18]}
    ],
    "style": {
      "series_colors": ["#B8BDC7", "#FF6B35"]
    }
  }'
```

In the current writer, the first color maps to the first series, the second color maps to the second series, and so on. It does not color individual bars within a single series.
