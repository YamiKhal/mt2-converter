from dataclasses import dataclass


@dataclass(frozen=True)
class Layout:
    size: int
    color: int | None
    normal: int | None
    texel: int | None


FORMATS = ("P", "PC", "PN", "PT", "PCN", "PCT", "PNT", "PCNT")


def layout(fmt: str) -> Layout:
    if fmt not in FORMATS:
        raise ValueError(f"unknown vertex format {fmt!r}")
    size = 3
    color = normal = texel = None
    if "C" in fmt:
        color = size
        size += 4
    if "N" in fmt:
        normal = size
        size += 3
    if "T" in fmt:
        texel = size
        size += 2

    return Layout(size, color, normal, texel)


def make_format(color: bool, normal: bool, texel: bool) -> str:
    return "P" + ("C" if color else "") + ("N" if normal else "") + ("T" if texel else "")
