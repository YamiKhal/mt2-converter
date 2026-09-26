import json
from pathlib import Path

import bpy

FILE_NAME = "swatch_profiles.json"

Color = tuple[float, float, float, float]


def profiles_file() -> Path:
    return Path(bpy.utils.extension_path_user(__package__, create=True)) / FILE_NAME


def read_profiles() -> dict[str, list[Color]]:
    try:
        stored = json.loads(profiles_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    profiles = stored.get("profiles", {}) if isinstance(stored, dict) else {}

    return {str(name): [_color(c) for c in colors if _is_color(c)]
            for name, colors in profiles.items() if isinstance(colors, list)}


def save_profile(name: str, colors: list[Color]):
    profiles = read_profiles()
    profiles[name] = [_color(c) for c in colors]
    _write(profiles)


def delete_profile(name: str):
    profiles = read_profiles()
    profiles.pop(name, None)
    _write(profiles)


def _write(profiles: dict[str, list[Color]]):
    target = profiles_file()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"profiles": profiles}, indent=1), encoding="utf-8")
    temporary.replace(target)


def _is_color(value) -> bool:
    return isinstance(value, list) and len(value) in (3, 4) and all(isinstance(c, (int, float)) for c in value)


def _color(value) -> Color:
    values = [min(max(float(c), 0.0), 1.0) for c in value]

    return tuple(values + [1.0] * (4 - len(values)))
