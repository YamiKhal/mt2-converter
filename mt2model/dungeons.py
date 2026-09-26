from dataclasses import dataclass, field

from . import records

THEMES_FOLDER = "dungeon/themes"
TILE_KINDS = {"walls": "d", "ceilings": "c"}
SHAPES = ("N", "NW", "NW_E", "NW_E_S", "NW_NE", "NW_NE_S", "NW_NE_SE", "NW_NE_SE_SW", "NW_S", "NW_SE",
          "N_E", "N_E_S", "N_E_S_W", "N_S", "O")


@dataclass
class Socket:
    tags: list[str] = field(default_factory=list)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


def tile_path(theme: str, kind: str, shape: str, extension: str = "vmb") -> str:
    return f"{THEMES_FOLDER}/{theme}/{kind}/{shape}/{TILE_KINDS[kind]}_{theme}_{shape}.{extension}"


def read_sockets(text: bytes | str) -> list[Socket]:
    tile = next((r for r in records.parse(text) if r.label == "mmoDungeonTileData"), None)
    container = tile.child("socket") if tile else None
    sockets = []
    for record in container.children_named("mmoTaggedSocket") if container else []:
        tag = record.child("tag")
        position = record.child("position")
        orientation = record.child("orientation")
        sockets.append(Socket(
            tags=tag.texts() + [t for c in tag.children for t in c.texts()] if tag else [],
            position=tuple(position.floats()[:3]) if position else (0.0, 0.0, 0.0),
            orientation=tuple(orientation.floats()[:4]) if orientation else (0.0, 0.0, 0.0, 1.0),
        ))

    return sockets


def write_sockets(sockets: list[Socket]) -> str:
    entries = [
        records.block(
            "mmoTaggedSocket",
            records.block("tag", *[records.leaf(None, t, semicolon=False) for t in s.tags]),
            records.Record("position", records.vector_line(s.position, semicolon=False).tokens, line_open=False),
            records.Record("orientation", records.vector_line(s.orientation, semicolon=False).tokens, line_open=False),
        )
        for s in sockets
    ]

    return records.render([records.block("mmoDungeonTileData", records.block("socket", *entries))])
