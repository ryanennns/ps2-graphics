# Models

When creating a new model, it must go under the ./models directory, and furthermore under the model family directory
to which you, the agent, belong to.

For instance, if I was Opus 5.5 designing a truck model, I would save my output as follows:

```
models
--> truck
------> claude-opus-5.5
----------> previews
--------------> asdf.png
----------> textures
--------------> xyz.png
----------> all_python_scripts_here.py
----------> truck.blend
```

models > particular_model > ai_model

## Python files in a model directory

A model directory contains exactly these four Python files and no others:

| File                 | Purpose                                                                                                                                                                      |
|----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `textures.py`        | Texture painters and the material table (texture, class, UV mapping) for this model                                                                                          |
| `build.py`           | Geometry, collections and placement. Builds textures and materials, bakes lighting, sets up the preview rig, saves `<model>.blend`. The only script that writes the `.blend` |
| `render_previews.py` | This model's extra review cameras (`EXTRA_CAMS`, `DEFAULT_CAM`), and rendering into `previews/`                                                                              |
| `validate.py`        | Triangle budgets for this model, and running the style self-check (exit 1 on failure)                                                                                        |

All model code must fit one of these four roles; no helper modules, scratch scripts or one-off
debug files. Shared code belongs in the repo-root `_lib/` and is imported from there, not copied.
Do not modify `_lib/` unless explicitly asked; see `_docs/technical/lib.md`. Notes go in a
`NOTES.md` next to the scripts (it's a doc, not code).

## Usage tracking (`usage.json`)

Save `usage.json` alongside the model's `.blend`, scripts and `NOTES.md` at
`models/<asset>/<ai_model>/usage.json`. Record the creation session's cumulative
usage, not just its last response, using exactly these five fields:

```json
{
  "model": "gpt-6.1-sol",
  "input": 39923,
  "output": 9647,
  "cached_input": 661760,
  "spend": 0
}
```

| Field | What to put there |
|-------|-------------------|
| `model` | AI model name matching the model directory name, not the asset name. |
| `input` | The session's recorded `tokens.input` counter. |
| `output` | The session's recorded `tokens.output` counter; do not add the separate reasoning counter. |
| `cached_input` | The session's recorded `tokens.cache.read` counter: cached input tokens, not the number of cache-hit requests. |
| `spend` | The session's recorded API cost in USD, or the calculated API-equivalent cost for subscription usage (see below), as a number without a currency symbol. |

For OpenCode, retrieve the creation session with
`rtk opencode api get /api/session/<sessionID>` and copy its cumulative counters
and cost into the fields above. Confirm that the session actually created this
asset; do not use a session that only inspected, renamed or validated an existing
model. Keep the session ID in `NOTES.md` for traceability, not as an extra JSON field.

Write valid JSON with numeric token counts and spending values. Preserve recorded
token counts and cost precision. Do not invent missing usage or substitute zero
for unknown values. If the creation session or required token stats cannot be
found, leave `usage.json` absent and explain that in `NOTES.md`.

### Subscription usage: calculate API-equivalent spending

For Claude, GPT or **any model used through a subscription**, a recorded zero or
missing API cost does not mean the work was free. Before finishing the model,
backfill `spend` with an API-equivalent calculation from the recorded token usage:

1. **Look up the exact model's current official API pricing online.** Use the
   applicable input, output, cache-read and cache-write rates, including cache TTL,
   prompt-length tiers, processing speed and regional modifiers where relevant.
   Do not substitute another model's prices or divide the subscription fee among models.
2. **Recover the creation session's usage.** Use cumulative counters or sum unique
   response records, never both. Claude Code can repeat the same response's usage
   across content parts: deduplicate by response/message ID before summing. Keep
   the JSON's recorded token counters unchanged and document their source and meaning.
3. **Calculate all billable token categories.** For rates quoted per million tokens:

   ```text
   spend = (uncached_input × input_rate
          + cached_input × cache_read_rate
          + cache_writes × cache_write_rate
          + billable_output × output_rate) / 1,000,000
   ```

   Split cache writes by TTL and requests by pricing tier when necessary, then sum
   the results. Prompt-length thresholds apply per request, not to session totals,
   and may count cached tokens. Include reasoning/thinking at the provider's output
   rate exactly once: add OpenCode's separate `tokens.reasoning` for billing, but
   do not add thinking again when Claude's `output_tokens` already includes it.
   Cache-write and reasoning counts used in the calculation belong in `NOTES.md`,
   not in extra JSON fields.
4. **Write the calculated USD amount to `spend`.** Keep it numeric and retain the
   five-field JSON format. Do not leave a zero placeholder when the calculation is
   possible. Preserve a genuine recorded API charge rather than replacing it with
   an estimate merely because it differs from today's list prices.
5. **Document and verify.** In the model's `NOTES.md`, record the session ID, pricing
   source URL and lookup date, rates, extra billable counters, formula and result.
   Label the result an **API-equivalent estimate**, not an actual invoice or
   subscription charge. State any assumptions or excluded/unavailable usage.
   Recalculate to verify the JSON amount and validate the JSON before committing.

If exact pricing or required billing details cannot be verified, do not fabricate
a price. Leave an existing recorded zero unchanged, explicitly mark it as
unresolved in `NOTES.md`, and report the blocker. If there is no recorded cost at
all, leave `usage.json` absent until it can be calculated; unknown is not zero.

When done with your model, commit your work as `${modelName}_${assetName}`
