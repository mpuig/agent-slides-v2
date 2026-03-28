# Layout Selection

Use this reference before choosing or overriding layouts.

## Isomorphism Principle

Match the layout to the shape of the idea.

- One claim with one body of proof -> `title_content`
- Two contrasted options -> `two_col` or `comparison`
- Three parallel points -> `three_col`
- One memorable statement -> `quote`
- Open and close with explicit `title` and `closing`

Do not choose layouts for decoration. Choose them because the structure helps the audience understand the argument faster.

## Layout Variety Rule

Avoid monotonous rhythm.

- Do not stack many identical content layouts in a row unless the repetition is intentional.
- Vary the visual pattern across the storyline: summary, comparison, proof, quote, close.
- Use repetition only when slides are deliberately comparable across the same frame.

## Auto vs Explicit Layout

Use `--auto-layout` when:

- the slide content already implies the structure
- you want the engine to choose the best fit from the payload
- the slide is a normal content slide

Use explicit `--layout` when:

- the slide has a fixed role like `title` or `closing`
- the comparison structure is known in advance
- a specific layout is required to preserve narrative rhythm
- auto-layout made a weak choice and you are correcting it

## Practical Heuristics

- `title_content` is the default for a single argument slide.
- `comparison` is stronger than `two_col` when the contrast is explicit and symmetric.
- `three_col` works only when each column stays short.
- `quote` should be rare. Use it to create emphasis, not to dump text.
- If content feels crowded, split the idea across slides instead of forcing denser layout choices.
