import os
import re
import sys
from pathlib import Path

GAME_FOLDER = "MMORPG Tycoon 2"
APP_ID = "486860"


def _steam_roots() -> list[Path]:
    roots = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        roots.append(Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam")
    else:
        home = Path.home()
        roots += [
            home / ".steam" / "steam",
            home / ".local" / "share" / "Steam",
            home / "Library" / "Application Support" / "Steam",
        ]

    return [r for r in roots if r.is_dir()]


def _library_folders(steam: Path) -> list[Path]:
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    folders = [steam]
    if vdf.is_file():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        folders += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]

    return folders


def find_game() -> Path | None:
    for steam in _steam_roots():
        for library in _library_folders(steam):
            game = library / "steamapps" / "common" / GAME_FOLDER
            if (game / "Data" / "MMORPG.zip").is_file():
                return game

    return None
