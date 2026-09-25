from dataclasses import dataclass


@dataclass(frozen=True)
class AssetType:
    key: str
    label: str
    description: str
    coloring: str
    keeps_nodes: bool
    special: frozenset[str]
    budget: int
    footprint_height: float | None


SCENERY_TYPES = (
    "tree", "tree_pine", "tree_palm", "tree_snow", "tree_swamp", "tree_redwood", "tree_savannah", "tree_feature",
    "cactus", "cactus_spiked", "cactus_feature", "bamboo", "tree_jungle", "sandstone", "tree_dead", "mushroom_giant",
    "mushroom", "crystal", "spike", "stone", "stone_large", "reed", "plant_small", "plant_medium", "cart", "chair",
    "post", "shelf", "table", "tower", "warfare", "water", "ice", "desert", "structure", "prop", "light",
    "wall_decorations", "festival", "xeno", "western", "confection", "ruin", "banner_stand", "eldritch", "volcanic",
    "tagged",
)

PLACEABLE_SCENERY_TYPES = SCENERY_TYPES[:-1]

MODULAR_SLOTS = (
    "sides", "sides_ground", "sides_decorated", "sides_decorated_ground", "sides_entrance", "tops_single", "tops_end",
    "tops_corner", "tops_straight", "tops_tee", "tops_cross", "underhang", "brace_single", "gap_single", "gap_general",
)

TAG_PLACES = {"floor": "f", "wall": "w", "ceiling": "c"}

TAG_KINDS = ("prop", "light")

SPECIAL_MATERIALS = frozenset({"light", "obstruction", "collision", "navmesh"})

ASSET_TYPES = {
    t.key: t
    for t in (
        AssetType("scenery", "Scenery", "A placeable object in one of the 47 scenery types",
                  "vertex", False, frozenset({"light"}), 25000, 10.0),
        AssetType("tagged", "Dungeon prop", "A prop the dungeon generator places in matching sockets",
                  "vertex", False, frozenset({"light"}), 10000, None),
        AssetType("weapon", "Weapon", "A weapon model; origin at the grip, blade along +Y (Blender +Z)",
                  "vertex", False, frozenset(), 5000, None),
        AssetType("building", "Building variant", "A new look for an existing building type",
                  "vertex", False, frozenset(), 40000, 2.0),
        AssetType("modular", "Modular building piece", "One piece of a modular building theme on a 3 x 3 x 3 cell",
                  "vertex", False, frozenset(), 6000, None),
        AssetType("wall", "Wall segment", "A wall segment along +Y (game +Z) from 0 to 50, or its turret",
                  "vertex", False, frozenset(), 10000, None),
        AssetType("costume_part", "Costume part", "A rigid part attached to one bone, colored by palette slots",
                  "costume", False, frozenset(), 5000, None),
        AssetType("raw", "Raw model", "Any model, exported as-is to a path you choose",
                  "any", True, SPECIAL_MATERIALS, 65535, None),
    )
}


def asset_type(key: str) -> AssetType:
    return ASSET_TYPES[key]


def guess_from_path(rel: str) -> str:
    parts = rel.split("/")
    if parts[0] == "scenery" and len(parts) == 3:
        return "tagged" if parts[1] == "tagged" else "scenery"
    if parts[0] == "weapons" and len(parts) == 3:
        return "weapon"
    if parts[0] == "costumes" and len(parts) == 3:
        return "costume_part"
    if parts[0] == "building_themes" and len(parts) == 4:
        return "modular"
    if parts[0] == "wall_themes" and len(parts) == 3:
        return "wall"
    if parts[0] == "buildings" and len(parts) == 3:
        return "building"

    return "raw"
