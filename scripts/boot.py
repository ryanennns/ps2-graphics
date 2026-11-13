"""Script bootstrap for asset scripts (models/<asset>/, scenes/<scene>/, or any project-specific depth).

Use these instead of hand-written sys.path boilerplate (works at any directory depth):

    import os, sys
    _d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(_d, "_lib")):
        _d = os.path.dirname(_d)
    sys.path.insert(0, _d)
    from _lib import boot
    HERE, REPO = boot.init(__file__)
    textures = boot.local(__file__, "textures")
    render_previews = boot.local(__file__, "render_previews")

Why: a long-lived Blender (the MCP add-on) keeps `sys.modules`. A plain `import textures` in a
second asset silently returns the FIRST asset's `textures` module. `local()` always loads the
sibling file by path, fresh, under a unique name. `init()` also finds the repo root by walking up
to the directory that contains `_lib/`, so scripts work at any depth.

To run any asset script inside a live Blender session (including older scripts that still use a
plain `import textures`), use `boot.run(path)`: it purges the stale sibling modules first.
"""
import importlib.util
import os
import sys

LOCAL_NAMES = ("textures", "render_previews", "build", "validate")


def find_repo(file):
    """Directory above `file` that contains `_lib/` (walks up; raises if none)."""
    d = os.path.dirname(os.path.abspath(file))
    while True:
        if os.path.isdir(os.path.join(d, "_lib")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError(f"no _lib/ found above {file}")
        d = parent


def init(file):
    """Put the repo root and the script's own dir on sys.path and purge stale sibling modules.
    Returns (HERE, REPO)."""
    here = os.path.dirname(os.path.abspath(file))
    repo = find_repo(file)
    for p in (repo, here):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    purge(here)
    return here, repo


def purge(here=None):
    """Drop cached asset-local modules (textures, render_previews, ...) that do not live in `here`
    (all of them if here is None), so the next plain `import textures` loads the right file."""
    for name in LOCAL_NAMES:
        m = sys.modules.get(name)
        f = getattr(m, "__file__", None) if m else None
        if m is not None and (here is None or not f or os.path.dirname(os.path.abspath(f)) != here):
            del sys.modules[name]


def local(file, name):
    """Load `<dir of file>/<name>.py` fresh, by path. The module is also registered as
    sys.modules[name] so the sibling scripts' own plain imports resolve to the same object."""
    here = os.path.dirname(os.path.abspath(file))
    path = os.path.join(here, name + ".py")
    uniq = "asset_" + os.path.relpath(here, find_repo(file)).replace(os.sep, "_").replace("-", "_").replace(".", "_") + "_" + name
    spec = importlib.util.spec_from_file_location(uniq, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[uniq] = mod
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(path, argv=()):
    """Execute an asset script as __main__ inside the current (possibly long-lived) Blender,
    with its dir on sys.path and stale sibling modules purged. `argv` is passed after '--'."""
    path = os.path.abspath(path)
    here = os.path.dirname(path)
    init(path)
    old_argv = sys.argv
    sys.argv = [path] + (["--", *argv] if argv else [])
    try:
        g = {"__file__": path, "__name__": "__main__"}
        with open(path) as fh:
            exec(compile(fh.read(), path, "exec"), g)
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
        purge()
    return here
