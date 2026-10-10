import zipfile
from pathlib import Path


class DirSource:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []

        return [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()


class ZipSource:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self._names = {n for n in self.zip.namelist() if not n.endswith("/")}

    def names(self) -> list[str]:
        return list(self._names)

    def exists(self, rel: str) -> bool:
        return rel in self._names

    def read(self, rel: str) -> bytes:
        return self.zip.read(rel)


class GameData:
    def __init__(self, sources: list):
        self.sources = sources
        self._names: list[str] | None = None
        self._overlay_names: list[str] | None = None

    @classmethod
    def open(cls, game: str | Path, overlays: list[str | Path] = ()) -> "GameData":
        return cls([DirSource(o) for o in overlays] + [_base_source(Path(game))])

    def names(self) -> list[str]:
        if self._names is None:
            self._names = sorted({n for s in self.sources for n in s.names()})

        return self._names

    def overlay_names(self) -> list[str]:
        if self._overlay_names is None:
            self._overlay_names = sorted({n for s in self.sources[:-1] for n in s.names()})

        return self._overlay_names

    def rescan(self):
        self._names = None
        self._overlay_names = None

    def files(self, prefix: str = "", suffix: str = "") -> list[str]:
        return [n for n in self.names() if n.startswith(prefix) and n.lower().endswith(suffix)]

    def exists(self, rel: str) -> bool:
        return any(s.exists(rel) for s in self.sources)

    def read(self, rel: str) -> bytes:
        for source in self.sources:
            if source.exists(rel):
                return source.read(rel)
        raise FileNotFoundError(rel)

    def materials(self) -> set[str]:
        return {n[len("materials/") : -len(".mat")] for n in self.files("materials/", ".mat") if n.count("/") == 1}

    def is_vanilla(self, rel: str) -> bool:
        return self.sources[-1].exists(rel)


def _base_source(game: Path):
    archive = game / "Data" / "MMORPG.zip"
    if archive.is_file():
        return ZipSource(archive)
    if game.suffix.lower() == ".zip" and game.is_file():
        return ZipSource(game)
    if game.is_dir():
        return DirSource(game)
    raise FileNotFoundError(f"no game data at {game}")
