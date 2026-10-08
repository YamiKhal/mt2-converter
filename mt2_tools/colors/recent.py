MAX_RECENT = 16


def remember_color(scene, color) -> None:
    recent = scene.mt2.recent_colors
    key = _key(color)
    for index in reversed(range(len(recent))):
        if _key(recent[index].color) == key:
            recent.remove(index)
    entry = recent.add()
    entry.color = color
    recent.move(len(recent) - 1, 0)
    while len(recent) > MAX_RECENT:
        recent.remove(len(recent) - 1)


def _key(color) -> tuple[int, ...]:
    return tuple(round(c * 255) for c in color)
