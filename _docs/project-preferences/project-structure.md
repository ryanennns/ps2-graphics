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
| `spend` | The session's recorded `cost` in USD, as a number without a currency symbol. |

For OpenCode, retrieve the creation session with
`rtk opencode api get /api/session/<sessionID>` and copy its cumulative counters
and cost into the fields above. Confirm that the session actually created this
asset; do not use a session that only inspected, renamed or validated an existing
model. Keep the session ID in `NOTES.md` for traceability, not as an extra JSON field.

Write valid JSON with numeric token counts and spending values. Preserve the
recorded precision and any recorded zero cost; a recorded `$0` is not proof that
the provider billed nothing. Do not estimate missing usage or substitute zero
for unknown values. If the creation session or required stats cannot be found,
leave `usage.json` absent and explain that in `NOTES.md`.

When done with your model, commit your work as `${modelName}_${assetName}`
