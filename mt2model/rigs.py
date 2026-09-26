from . import records
from .animations import Animation

SEQUENCES = ("attack", "attack_double", "attack_heavy", "attack_spin", "attack_headbutt", "attack_shot", "attack_bow",
             "cast", "cast_force", "cast_charge", "cast_swish")

CHARACTER_ANIMATIONS = (
    "idle", "idle_combat", "run", "jump",
    *(f"{sequence}_{step}" for sequence in SEQUENCES for step in ("start", "loop", "end")),
    "socialise", "levelup", "ride",
    "sit_start", "sit_loop", "sit_end", "stun_start", "stun_loop", "stun_end",
    "death", "ghost", "roar",
)

STANDARD_BONES = ("head", "hat", "torso", "tail", "armleft", "armright", "legleft", "legright")

GIZMO_ANIMATIONS = ("open", "close", "unlock")

CREATURE_FOLDERS = {
    "monster": "default/monsters",
    "npc": "default/npcs",
    "class": "default/classes",
    "dungeon_boss": "default/dungeonbosses",
}


def merge_animations(base: list[Animation], changed: list[Animation]) -> list[Animation]:
    by_name = {a.name: a for a in changed}
    merged = [by_name.pop(a.name, a) for a in base]

    return merged + list(by_name.values())


def rename_nodes(animations: list[Animation], renames: dict[str, str]) -> list[Animation]:
    for animation in animations:
        for timeline in animation.timelines:
            timeline.node = renames.get(timeline.node, timeline.node)

    return animations


def missing_animations(names: set[str], needed: tuple[str, ...]) -> list[str]:
    return [n for n in needed if n not in names]


def creature_type(template: bytes | str, name: str, costume: str) -> str:
    parsed = records.parse(template)
    owner = next((r for r in parsed if r.label == "mmoCharacterType"), None)
    definition = owner.child("def") if owner else None
    if definition is None:
        raise ValueError("not a creature type file: no mmoCharacterType def")
    definition.set_prop("name", name)
    definition.set_prop("costumeName", costume)

    return records.render(parsed)


def creature_costume(template: bytes | str) -> str | None:
    owner = next((r for r in records.parse(template) if r.label == "mmoCharacterType"), None)
    definition = owner.child("def") if owner else None

    return definition.prop("costumeName") if definition else None
