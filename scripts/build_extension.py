import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "blender" / "mt2_tools"
LIBRARY = ROOT / "mt2model"
BUILD = ROOT / "build" / "mt2_tools"
DIST = ROOT / "dist"


def _ignore(directory, names):
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]


def assemble() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    shutil.copytree(SOURCE, BUILD, ignore=_ignore)
    shutil.copytree(LIBRARY, BUILD / "mt2model", ignore=_ignore)

    return BUILD


def version() -> str:
    text = (SOURCE / "blender_manifest.toml").read_text(encoding="utf-8")

    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def package(folder: Path) -> Path:
    DIST.mkdir(exist_ok=True)
    archive = DIST / f"mt2_tools-{version()}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(folder).as_posix())

    return archive


def main():
    folder = assemble()
    print(f"assembled {folder}")
    if "--no-zip" not in sys.argv:
        print(f"wrote {package(folder)}")


if __name__ == "__main__":
    main()
