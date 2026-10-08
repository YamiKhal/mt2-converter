# Contributing

## Layout

```
mt2model/                 the library: reads, writes and checks game files; no dependencies, no Blender
mt2_tools/                the Blender extension (the build copies mt2model into it)
  __init__.py             registers everything
  blender_manifest.toml   extension id, version, permissions
  game.py                 the game's data and the mod folder settings, cached
  mod_folder.py           reading and writing files in the mod folder
  preferences.py          add-on preferences (game folder, update check)
  properties.py           the scene and object settings the panels show
  panels.py               the MT2 sidebar tab
  updates.py              asks GitHub for a newer release
  guides.py               viewport overlays
  operators/              one file per group of buttons (import, export, paint, helpers, …)
  objects/                creating and reading the helper objects in a scene (bones, pads, sockets, …)
  conversion/             to_blender.py and to_game.py: game models ⇄ Blender meshes
  export/                 planning an export: which files, which checks (pipeline.py, then one file per asset family)
  materials/              Blender previews of game materials, palettes, textured materials
  colors/                 recent colors and swatch profiles
tests/                    library tests (unittest, no game or Blender needed)
tests/blender/            Blender tests: run.py installs the built zip into a throwaway Blender and runs suite.py
scripts/                  build, version bump and release
examples/                 sample files used by docs and tests
```

## Setup

Python 3.11 or newer, Blender 5.1 for the Blender tests, and the game for the round-trip tests.

```bat
python -m pip install ruff
```

## Checks

```bat
python -m ruff check .                 # lint
python -m ruff format .                # format (black style, 120 columns)
python -m unittest discover -s tests   # library tests
python tests/blender/run.py            # Blender tests; add --full or --all for game model round trips
python scripts/build_extension.py      # build/ and dist/mt2_tools-<version>.zip
```

- Set `BLENDER` to use a Blender other than `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`.
- The Blender tests use a throwaway Blender user folder, so your own Blender setup is untouched.

## Code style

- `ruff format` decides the formatting; `ruff check` must pass.
- Clear names over comments: a comment explains *why*, never *what*.
- A blank line before `return` when the function has more than one statement, and between steps of a longer function.
- Type hints on functions that other modules call.
- One job per file. Anything that touches Blender goes in `mt2_tools`; everything else goes in `mt2model`, where it can be tested without Blender.
- UI text: US spelling (*color*), *enabled/disabled* rather than *on/off*, details in tooltips rather than labels.

## Releasing

1. `python scripts/bump_version.py 0.6.0` sets the version in `mt2_tools/blender_manifest.toml` and `mt2model/__init__.py`. The build refuses to run if they differ.
2. Add a `## MT2 Tools Patch - 0.6.0` section to [CHANGELOG.md](CHANGELOG.md), with `### New` and `### Fixed`.
3. Commit and push.
4. `python scripts/release.py` builds the zip and publishes GitHub release `v0.6.0` with that changelog section as its notes. It needs the [GitHub CLI](https://cli.github.com) (`gh auth login` once).

Installed copies of MT2 Tools find the release on their next start and offer the update.
