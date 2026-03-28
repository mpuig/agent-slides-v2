# Chart Guide

Use this reference before adding a chart.

## When To Use A Chart

Add a chart only when a visual comparison proves the claim better than plain text.

Good uses:

- trend over time
- comparison across categories
- part-to-whole split
- relationship between variables

Bad uses:

- a chart that merely repeats obvious numbers
- decorative charts without a claim
- complex data that the audience cannot parse on one slide

## Pick The Right Chart Type

- `bar` or `column`: compare categories
- `line`: show change over time
- `pie` or `doughnut`: part-to-whole, only when there is a single clear series
- `scatter`: show relationship or clustering
- `area`: emphasize cumulative magnitude over time

## Build Rules

- Give the chart an action-title slide and, when useful, a chart title.
- Keep the data payload simple and readable.
- Use the chart as evidence for a claim already stated on the slide.
- Include the source for the data on the slide or in supporting content.

## CLI

Use the shipped chart command:

```bash
uv run agent-slides chart add deck.json --slide 2 --slot body --type bar --data '{"categories":["Q1","Q2"],"series":[{"name":"Revenue","values":[12,18]}]}'
```

`chart add` creates or replaces the chart node in the target slot.

## Quality Check

Before you keep a chart, ask:

- What claim does this chart prove?
- Is the chosen chart type the clearest match?
- Could the audience understand it in a few seconds?
- Is the source present?
