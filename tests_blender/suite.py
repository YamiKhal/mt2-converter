import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
ARCHIVE, SANDBOX = ARGS[0], Path(ARGS[1])
STEP = 1 if "--all" in ARGS else 10 if "--full" in ARGS else 0
PACKAGE = "bl_ext.user_default.mt2_tools"

bpy.ops.extensions.package_install_files(filepath=ARCHIVE, repo="user_default", enable_on_install=True)


def module(name: str):
    return importlib.import_module(f"{PACKAGE}.{name}")


pipeline = module("pipeline")
game = module("game")
model = module("mt2model.model")
formats = module("mt2model.formats")
detect = module("mt2model.detect")
records = module("mt2model.records")
obstruction = module("mt2model.obstruction")

GAME = detect.find_game()
PROJECT = Path(tempfile.mkdtemp(prefix="mt2_project_", dir=SANDBOX))

SAMPLES = (
    "scenery/tree/p_ext_tree_01.vmb",
    "scenery/desert/bones_eldritch_1.vmb",
    "scenery/tagged/f_light_classic_brazier.vmb",
    "weapons/swords/015_sword_basic1.vmb",
    "costumes/knight/head.vmb",
    "costumes/knight/torso.vmb",
    "building_themes/castle2/sides/b_w_castle2_blank.vmb",
    "wall_themes/castle/wall_castle.vmb",
    "buildings/tavern/base.vmb",
    "buildings/inn/base.vmb",
    "gizmo/door/base1.vmb",
    "dungeon/themes/arid/walls/N/d_arid_N.vmb",
    "skeletons/humanoid.vmb",
)

NORMAL_OUTLIERS = 0.005
TOLERANCE = {"position": 2e-3, "color": 2.5 / 255, "normal": 1e-2, "uv": 2e-3}


def reset_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    bpy.context.scene.mt2.findings.clear()


def parts(fragment, index):
    lay = formats.layout(fragment.format)
    v = fragment.vertices[index]
    out = {"position": v[:3]}
    if lay.color is not None:
        out["color"] = v[lay.color:lay.color + 4]
    if lay.normal is not None:
        n = v[lay.normal:lay.normal + 3]
        length = sum(x * x for x in n) ** 0.5 or 1.0
        out["normal"] = tuple(x / length for x in n)
    if lay.texel is not None:
        out["uv"] = v[lay.texel:lay.texel + 2]

    return out


def triangles(root):
    for node, depth in root.walk():
        points = [v[:3] for f in node.fragments for v in f.vertices]
        span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)) if points else 1.0
        span = span or 1.0
        for fragment in node.fragments:
            for k in range(0, len(fragment.indices) // 3 * 3, 3):
                ids = fragment.indices[k:k + 3]
                if len(set(ids)) == 3 and area(*(fragment.vertices[i][:3] for i in ids)) > 1e-9 * span * span:
                    corners = [parts(fragment, i) for i in ids]
                    for corner in corners:
                        corner["position"] = tuple(x / span for x in corner["position"])
                    yield node.name, depth, fragment.material, corners


def area(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    w = [c[i] - a[i] for i in range(3)]
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])

    return sum(x * x for x in cross) ** 0.5


def canonical(tri):
    keys = [tuple(round(x, 2) for x in c["position"]) for c in tri]
    start = min(range(3), key=keys.__getitem__)

    return tuple(keys[start:] + keys[:start]), tri[start:] + tri[:start]


def assert_same_geometry(case, original, exported, compare_uv: bool):
    pool = {}
    for name, depth, material, tri in triangles(exported):
        key, ordered = canonical(tri)
        pool.setdefault((depth, material, key), []).append(ordered)
    missing = total = normal_outliers = 0
    worst = {k: 0.0 for k in TOLERANCE}
    for name, depth, material, tri in triangles(original):
        key, ordered = canonical(tri)
        candidates = pool.get((depth, material, key))
        if not candidates:
            missing += 1
            continue

        def error(candidate):
            result = {}
            for kind in TOLERANCE:
                if kind == "uv" and not compare_uv:
                    continue
                if material == "light" and kind != "position":
                    continue
                if all(kind in c for c in ordered) and all(kind in c for c in candidate):
                    result[kind] = max(abs(a - b) for x, y in zip(ordered, candidate) for a, b in zip(x[kind], y[kind]))

            return result

        best = min(candidates, key=lambda c: sum(error(c).values()))
        candidates.remove(best)
        total += 1
        for kind, value in error(best).items():
            if kind == "normal" and value > TOLERANCE[kind]:
                normal_outliers += 1
            else:
                worst[kind] = max(worst[kind], value)
    case.assertEqual(missing, 0, f"{missing} triangles missing or moved")
    for kind, value in worst.items():
        case.assertLessEqual(value, TOLERANCE[kind], f"{kind} differs by {value}")
    case.assertLessEqual(normal_outliers, max(2, total * NORMAL_OUTLIERS), f"{normal_outliers} of {total} triangles have normals off")


def run(operator, **properties):
    try:
        return operator(**properties)
    except RuntimeError:
        return {"CANCELLED"}


def import_game(rel):
    bpy.ops.mt2.import_game(model=rel)

    return bpy.context.view_layer.objects.active


def select_only(obj):
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def add_cube(name, size=2.0, location=(0, 0, 1)):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.active_object
    obj.name = name

    return obj


def select_faces(obj, indices):
    select_only(obj)
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for index in indices:
        obj.data.polygons[index].select = True
    obj.data.polygons.active = indices[0]
    bpy.ops.object.mode_set(mode="EDIT")


def selected_faces(obj):
    bpy.ops.object.mode_set(mode="OBJECT")
    chosen = [p.index for p in obj.data.polygons if p.select]
    bpy.ops.object.mode_set(mode="EDIT")

    return chosen


def game_material(obj, name):
    select_only(obj)
    bpy.ops.mt2.setup_material(name=name)


class Setup(unittest.TestCase):
    def test_extension_installed_and_paths_set(self):
        self.assertIsNotNone(GAME, "game install not found")
        self.assertIn(PACKAGE, bpy.context.preferences.addons)
        self.assertIsNotNone(game.game_data())


class RoundTrip(unittest.TestCase):
    def setUp(self):
        reset_scene()
        bpy.context.scene.mt2.mod_id = "roundtrip"

    def check_round_trip(self, rel):
        data = game.game_data()
        original = model.read_model(data.read(rel))
        obj = import_game(rel)
        plan = pipeline.plan(obj)
        self.assertIsNotNone(plan.built, [f.message for f in plan.findings])
        compare_uv = any("costume" in f.material or "dungeon" in f.material for n, _ in original.walk() for f in n.fragments)
        assert_same_geometry(self, original, plan.built.root, compare_uv)
        self.assertEqual(sum(1 for _ in original.walk()), sum(1 for _ in plan.built.root.walk()))

    def test_samples(self):
        for rel in SAMPLES:
            with self.subTest(rel=rel):
                reset_scene()
                self.check_round_trip(rel)

    def test_game_models(self):
        if not STEP:
            self.skipTest("pass --full (every 10th game model) or --all")
        for rel in game.game_data().files("", ".vmb")[::STEP]:
            with self.subTest(rel=rel):
                reset_scene()
                self.check_round_trip(rel)

    def test_clearing_custom_normals_wins_over_original_normals(self):
        obj = import_game("costumes/knight/head.vmb")
        select_only(obj)
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        bpy.ops.object.shade_flat()
        fragment = pipeline.plan(obj).built.root.fragments[0]
        for k in range(0, len(fragment.indices), 3):
            a, b, c = (fragment.vertices[i] for i in fragment.indices[k:k + 3])
            u = [b[i] - a[i] for i in range(3)]
            w = [c[i] - a[i] for i in range(3)]
            face = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            length = sum(x * x for x in face) ** 0.5
            normal = a[3:6]
            self.assertLess(sum(x / length * n for x, n in zip(face, normal)), -0.999)

    def test_obstruction_and_light_are_imported_as_helpers(self):
        obj = import_game("scenery/desert/bones_eldritch_1.vmb")
        roles = sorted(child.mt2.role for child in obj.children)
        self.assertIn("OBSTRUCTION", roles)
        plan = pipeline.plan(obj)
        original = obstruction.read_obstruction(game.game_data().read("scenery/desert/bones_eldritch_1_obs.vrt").decode())
        self.assertEqual(len(plan.built.obstruction), len(original))
        for a, b in zip(plan.built.obstruction, original):
            for p, q in zip(a, b):
                self.assertAlmostEqual(p[0], q[0], places=4)
                self.assertAlmostEqual(p[1], q[1], places=4)
        brazier = import_game("scenery/tagged/f_light_classic_brazier.vmb")
        self.assertIn("LIGHT", [c.mt2.role for c in brazier.children])
        original = model.read_model(game.game_data().read("scenery/tagged/f_light_classic_brazier.vmb"))
        exported = pipeline.plan(brazier).built.root
        colors = [next(f for f in root.fragments if f.material == "light").vertices[0][3:7] for root in (original, exported)]
        for a, b in zip(*colors):
            self.assertAlmostEqual(a, b, places=4)


class NewModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy.context.scene.mt2.project_dir = str(PROJECT)
        bpy.context.scene.mt2.mod_id = ""
        bpy.ops.mt2.create_project(mod_name="Test Models", author="tests")

    def setUp(self):
        reset_scene()
        for obj in PROJECT.rglob("*.vmb"):
            obj.unlink()

    def test_manifest_created(self):
        manifest = json.loads((PROJECT / "manifest.json").read_text())
        self.assertEqual(manifest["id"], "test_models")
        self.assertEqual(bpy.context.scene.mt2.mod_id, "test_models")

    def test_scenery_export_with_light_and_obstruction(self):
        cube = add_cube("Rock", size=4.0, location=(10, 5, 2))
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.paint_color = (0.5, 0.25, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.mt2.make_asset()
        cube.mt2.scenery_type = "stone"
        bpy.context.scene.cursor.location = (10, 5, 3)
        bpy.ops.mt2.add_light(radius=15.0)
        select_only(cube)
        bpy.ops.mt2.add_obstruction(size=3.0)
        select_only(cube)
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        path = PROJECT / "scenery/stone/test_models_rock.vmb"
        root = model.load(path)
        materials = sorted(f.material for f in root.fragments)
        self.assertEqual(materials, ["Material_tint", "light"])
        tint = next(f for f in root.fragments if f.material == "Material_tint")
        self.assertEqual(tint.format, "PCN")
        ys = [v[1] for v in tint.vertices]
        self.assertAlmostEqual(min(ys), -2.0, places=4)
        self.assertAlmostEqual(max(ys), 2.0, places=4)
        self.assertAlmostEqual(tint.vertices[0][3], 128 / 255, places=3)
        self.assertAlmostEqual(tint.vertices[0][4], 64 / 255, places=3)
        light = next(f for f in root.fragments if f.material == "light")
        corners = [v[:3] for v in light.vertices]
        diagonal = sum((max(c[i] for c in corners) - min(c[i] for c in corners)) ** 2 for i in range(3)) ** 0.5
        self.assertAlmostEqual(diagonal * 0.375, 15.0, places=3)
        centre_y = (max(c[1] for c in corners) + min(c[1] for c in corners)) / 2
        self.assertAlmostEqual(centre_y, 1.0, places=3)
        obs = (PROJECT / "scenery/stone/test_models_rock_obs.vrt").read_text()
        self.assertEqual(len(obstruction.read_obstruction(obs)), 1)
        log = json.loads((PROJECT / ".mt2export.json").read_text())
        self.assertIn("scenery/stone/test_models_rock.vmb", log)

    def test_axes_map_blender_to_game(self):
        mesh = bpy.data.meshes.new("tri")
        mesh.from_pydata([(1, 2, 3), (2, 2, 3), (1, 3, 3)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new("Tri", mesh)
        bpy.context.collection.objects.link(obj)
        select_only(obj)
        game_material(obj, "Material_tint")
        bpy.ops.mt2.make_asset()
        obj.mt2.asset = "raw"
        obj.mt2.raw_path = "scenery/stone/tri.vmb"
        plan = pipeline.plan(obj)
        fragment = plan.built.root.fragments[0]
        positions = [fragment.vertices[i][:3] for i in fragment.indices]
        self.assertEqual([tuple(round(x, 5) for x in p) for p in positions], [(-1, 3, 2), (-1, 3, 3), (-2, 3, 2)])
        normal = fragment.vertices[fragment.indices[0]][7:10]
        self.assertAlmostEqual(normal[1], 1.0, places=4)
        a, b, c = (Vector(p) for p in positions)
        self.assertLess((b - a).cross(c - a).dot(Vector(normal)), 0, "game triangles are clockwise")

    def test_costume_part_palette_and_normalise(self):
        cube = add_cube("Hat", size=2.0, location=(0, 0, 0))
        game_material(cube, "costume")
        bpy.ops.mt2.palette_slot(slot=3)
        bpy.context.scene.mt2.shade = 0.4
        bpy.ops.mt2.shade(gradient=False)
        bpy.ops.mt2.make_asset()
        cube.mt2.asset = "costume_part"
        cube.mt2.costume_set = "test_models_knight"
        cube.mt2.bone = "hat"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        root = model.load(PROJECT / "costumes/test_models_knight/hat.vmb")
        fragment = root.fragments[0]
        self.assertEqual((fragment.material, fragment.format), ("costume", "PNT"))
        self.assertTrue(all(abs(v[6] - 2.5 / 8) < 1e-6 and abs(v[7] - 0.4) < 1e-6 for v in fragment.vertices))
        extent = max(max(v[i] for v in fragment.vertices) - min(v[i] for v in fragment.vertices) for i in range(3))
        self.assertAlmostEqual(extent, 1.0, places=5)
        self.assertAlmostEqual(cube.mt2.model_scale, 2.0, places=5)

    def test_edit_mode_fill_touches_only_selected_faces(self):
        cube = add_cube("Painted")
        game_material(cube, "Material_tint")
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        cube.data.polygons[0].select = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.object.mode_set(mode="OBJECT")
        colors = [tuple(round(c, 3) for c in d.color_srgb) for d in cube.data.color_attributes.active_color.data]
        red = sum(1 for c in colors if c == (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(red, cube.data.polygons[0].loop_total)

    def test_select_same_color_and_recent_colors(self):
        cube = add_cube("Two reds")
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.recent_colors.clear()
        bpy.context.scene.mt2.paint_color = (1.0, 1.0, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        normals = [tuple(round(x) for x in p.normal) for p in cube.data.polygons]
        opposite = normals.index(tuple(-x for x in normals[0]))
        select_faces(cube, [0, opposite])
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.mt2.fill_color()
        self.assertEqual([tuple(round(c, 3) for c in e.color) for e in bpy.context.scene.mt2.recent_colors],
                         [(1.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)])
        select_faces(cube, [0])
        bpy.context.scene.mt2.paint_color = (0.0, 0.0, 1.0, 1.0)
        bpy.ops.mt2.pick_color()
        self.assertEqual(tuple(round(c, 3) for c in bpy.context.scene.mt2.paint_color), (1.0, 0.0, 0.0, 1.0))
        bpy.context.scene.mt2.select_connected = True
        bpy.ops.mt2.select_color()
        self.assertEqual(selected_faces(cube), [0])
        bpy.context.scene.mt2.select_connected = False
        bpy.ops.mt2.select_color()
        self.assertEqual(selected_faces(cube), sorted([0, opposite]))
        select_faces(cube, [1 if opposite != 1 else 2])
        bpy.context.scene.mt2.select_connected = True
        bpy.ops.mt2.select_color()
        self.assertEqual(len(selected_faces(cube)), 4)
        bpy.ops.object.mode_set(mode="OBJECT")

    def test_missing_material_blocks_export(self):
        cube = add_cube("Broken")
        material = bpy.data.materials.new("Broken")
        material.mt2.game_name = "NotAMaterial"
        cube.data.materials.append(material)
        select_only(cube)
        bpy.ops.mt2.make_asset()
        self.assertEqual(run(bpy.ops.mt2.export), {"CANCELLED"})
        self.assertTrue(any("closes" in f.message for f in bpy.context.scene.mt2.findings))

    def test_rename_after_export_is_blocked(self):
        cube = add_cube("Stable", size=4.0, location=(0, 0, 2))
        game_material(cube, "Material_tint")
        bpy.ops.mt2.make_asset()
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})
        cube.mt2.name = "renamed"
        self.assertEqual(run(bpy.ops.mt2.export), {"CANCELLED"})
        cube.mt2.exported_path = ""
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})

    def test_building_variant_is_derived(self):
        obj = import_game("buildings/tavern/base.vmb")
        obj.mt2.name = "blue"
        obj.mt2.display_name = "Blue Tavern"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        variant = records.parse((PROJECT / "buildings/tavern/test_models_blue.variant").read_text())[0]
        self.assertEqual(variant.prop("name"), "test_models_blue")
        self.assertEqual(variant.prop("modelFile"), "buildings/tavern/test_models_blue.vmb")
        self.assertIsNotNone(variant.child("pad"))
        strings = (PROJECT / "i18n/english/test_models_models.vrt").read_text()
        self.assertIn('building_variant_tavern_test_models_blue_displayname "Blue Tavern"', strings)

    def test_weapon_path_and_footprint_preview(self):
        sword = add_cube("Blade", size=0.2, location=(0, 0, 0.5))
        game_material(sword, "Material_tint")
        bpy.ops.mt2.make_asset()
        sword.mt2.asset = "weapon"
        sword.mt2.weapon_category = "swords"
        sword.mt2.item_level = 45
        self.assertEqual(pipeline.plan(sword).rel, "weapons/swords/045_test_models_blade.vmb")
        tower = add_cube("Tower", size=6.0, location=(0, 0, 3))
        game_material(tower, "Material_tint")
        bpy.ops.mt2.make_asset()
        bpy.ops.mt2.footprint_preview()
        self.assertTrue(any(c.mt2.role == "PREVIEW" for c in tower.children))
        self.assertTrue(pipeline.plan(tower).ok)

    def test_new_weapon_category_gets_a_name(self):
        blade = add_cube("Blade", size=0.2, location=(0, 0, 0.5))
        game_material(blade, "Material_tint")
        bpy.ops.mt2.make_asset()
        blade.mt2.asset = "weapon"
        blade.mt2.weapon_category = "test_blades"
        self.assertTrue(any("<<weapon_category_test_blades>>" in f.message for f in pipeline.plan(blade).findings))
        blade.mt2.display_name = "Test Blades"
        plan = pipeline.plan(blade)
        self.assertIn('weapon_category_test_blades "Test Blades"', plan.texts["i18n/english/test_models_models.vrt"])

    def test_two_assets_cannot_share_a_path(self):
        for name in ("Twin", "Twin.001"):
            twin = add_cube(name, size=3.0)
            game_material(twin, "Material_tint")
            bpy.ops.mt2.make_asset()
            twin.mt2.name = "twin"
        messages = [f.message for f in pipeline.plan(twin).findings if f.level == "error"]
        self.assertTrue(any("also exports to" in m for m in messages), messages)

    def test_picking_a_game_material_leaves_other_objects_alone(self):
        first, second = add_cube("First", location=(0, 0, 1)), add_cube("Second", location=(5, 0, 1))
        for cube in (first, second):
            game_material(cube, "Material_tint")
        select_only(first)
        bpy.ops.mt2.pick_game_material(slot=0, name="emissive")
        self.assertEqual(first.material_slots[0].material.mt2.game_name, "emissive")
        self.assertEqual(second.material_slots[0].material.mt2.game_name, "Material_tint")

    def test_new_textured_material(self):
        cube = add_cube("Crate", size=3.0)
        select_only(cube)
        checker = Path(__file__).resolve().parent.parent / "examples" / "checker.png"
        self.assertEqual(run(bpy.ops.mt2.new_textured_material, filepath=str(checker), material_name="crate"),
                         {"FINISHED"})
        self.assertTrue((PROJECT / "textures/test_models_crate.png").is_file())
        mat = (PROJECT / "materials/test_models_crate.mat").read_text()
        self.assertLess(mat.index("texture"), mat.index("shader"))
        self.assertEqual(cube.material_slots[0].material.mt2.game_name, "test_models_crate")
        bpy.ops.mt2.make_asset()
        cube.mt2.name = "crate"
        plan = pipeline.plan(cube)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(plan.built.root.fragments[0].format, "PCNT")
        texture = PROJECT / "textures/test_models_crate.png"
        texture.rename(texture.with_name("moved.png"))
        run(bpy.ops.mt2.check)
        self.assertTrue(any("isn't in the game" in f.message for f in bpy.context.scene.mt2.findings))
        texture.with_name("moved.png").rename(texture)
        self.assertEqual(run(bpy.ops.mt2.new_textured_material, filepath=str(checker), material_name="crate"),
                         {"CANCELLED"})

    def test_edit_mode_without_selection_changes_nothing(self):
        cube = add_cube("Untouched")
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.paint_color = (1.0, 1.0, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        select_faces(cube, [0])
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        self.assertEqual(run(bpy.ops.mt2.fill_color), {"CANCELLED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        colors = {tuple(round(c, 3) for c in d.color_srgb) for d in cube.data.color_attributes.active_color.data}
        self.assertEqual(colors, {(1.0, 1.0, 1.0, 1.0)})

    def test_bake_texture_to_colors(self):
        bpy.ops.mesh.primitive_plane_add(size=2)
        plane = bpy.context.active_object
        image = bpy.data.images.new("tex", 4, 4)
        image.pixels = [0.0, 1.0, 0.0, 1.0] * 16
        material = bpy.data.materials.new("textured")
        if material.node_tree is None:
            material.use_nodes = True
        nodes = material.node_tree.nodes
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        material.node_tree.links.new(texture.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
        plane.data.materials.append(material)
        self.assertEqual(bpy.ops.mt2.bake_colors(), {"FINISHED"})
        colors = [tuple(d.color_srgb) for d in plane.data.color_attributes.active_color.data]
        self.assertTrue(all(c[1] > 0.9 and c[0] < 0.1 for c in colors), colors[:2])


class FakeLayout:
    def __init__(self, case, log):
        self.case, self.log = case, log

    def _child(self, *args, **kwargs):
        return FakeLayout(self.case, self.log)

    row = column = box = grid_flow = _child

    def separator(self, *args, **kwargs):
        pass

    def label(self, *args, **kwargs):
        self.log.append(("label", kwargs.get("text", "")))

    def prop(self, data, name, **kwargs):
        self.case.assertIn(name, data.bl_rna.properties.keys(), f"missing property {name}")
        self.log.append(("prop", name))

    def prop_search(self, data, name, search_data, search_name, **kwargs):
        self.case.assertIn(name, data.bl_rna.properties.keys())
        self.case.assertTrue(hasattr(search_data, search_name))

    def template_list(self, *args, **kwargs):
        self.log.append(("list", args[0]))

    def operator(self, idname, **kwargs):
        category, name = idname.split(".")
        self.case.assertTrue(hasattr(getattr(bpy.ops, category), name), f"missing operator {idname}")
        self.log.append(("operator", idname))

        return type("Properties", (), {})()


class UI(unittest.TestCase):
    def draw_all(self):
        log = []
        ui = module("ui")
        for panel in ui.CLASSES:
            if hasattr(panel, "poll") and not panel.poll(bpy.context):
                continue
            fake = type("Panel", (), {"layout": FakeLayout(self, log)})()
            panel.draw(fake, bpy.context)

        return log

    def test_panels_draw_without_an_asset(self):
        reset_scene()
        log = self.draw_all()
        self.assertIn(("operator", "mt2.make_asset"), log)
        self.assertIn(("operator", "mt2.import_game"), log)

    def test_every_icon_exists(self):
        icons = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        folder = Path(module("ui").__file__).parent
        for path in folder.glob("*.py"):
            for icon in re.findall(r'icon\s*=\s*"([A-Z0-9_]+)"', path.read_text()):
                self.assertIn(icon, icons, f"{path.name}: {icon}")
        for icon in module("ui").LEVEL_ICONS.values():
            self.assertIn(icon, icons)

    def test_findings_only_show_for_their_asset(self):
        reset_scene()
        broken = add_cube("Broken")
        bpy.ops.mt2.make_asset()
        run(bpy.ops.mt2.check)
        self.assertTrue(bpy.context.scene.mt2.findings)
        message = bpy.context.scene.mt2.findings[0].message
        self.assertTrue(any(message.startswith(text) for kind, text in self.draw_all() if kind == "label" and text))
        other = add_cube("Other", location=(5, 0, 1))
        bpy.ops.mt2.make_asset()
        self.assertFalse(any(text and message.startswith(text) for kind, text in self.draw_all() if kind == "label"))
        select_only(broken)
        broken.mt2.name = "renamed"
        self.assertFalse(bpy.context.scene.mt2.findings)

    def test_panels_draw_for_every_asset_type(self):
        reset_scene()
        bpy.context.scene.mt2.mod_id = "ui_test"
        cube = add_cube("UI")
        game_material(cube, "Material_tint")
        bpy.ops.mt2.make_asset()
        for asset in module("mt2model.assets").ASSET_TYPES:
            with self.subTest(asset=asset):
                cube.mt2.asset = asset
                log = self.draw_all()
                self.assertIn(("operator", "mt2.export"), log)


def main():
    game.preferences().game_path = str(GAME) if GAME else ""
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for case in (Setup, RoundTrip, NewModels, UI):
        suite.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


main()
