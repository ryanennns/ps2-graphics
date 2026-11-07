# Models

When creating a new model, it must go under the ./models directory, and furthermore under the model family directory
to which you, the agent, belong to.

For instance, if I was Opus 5.5 designing a truck model, I would save my output as follows:

```
models
--> claude
------> truck
----------> previews
--------------> asdf.png
----------> textures
--------------> xyz.png
----------> all_python_scripts_here.py
----------> truck.blend
```
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
